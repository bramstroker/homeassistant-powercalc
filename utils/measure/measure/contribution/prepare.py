from __future__ import annotations

from collections.abc import Callable
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from measure.contribution.models import ContributionMetadata, ContributionPreparedFile, ContributionPreview

JsonValidator = Callable[[dict[str, Any], dict[str, Any]], None]


class ProfilePreparationError(ValueError):
    pass


class ProfilePreparer:
    """Prepare generated profile artifacts for a profile-library pull request."""

    def __init__(
        self,
        *,
        library_root: Path,
        model_schema_path: Path,
        validator: JsonValidator | None = None,
    ) -> None:
        self.library_root = library_root
        self.model_schema_path = model_schema_path
        self.validator = validator or _jsonschema_validate

    def prepare(self, artifact_directory: Path, metadata: ContributionMetadata) -> ContributionPreview:
        artifact_directory = artifact_directory.resolve()
        if not artifact_directory.is_dir():
            raise ProfilePreparationError("Artifact directory does not exist")

        files = self._artifact_files(artifact_directory)
        model_path = artifact_directory / "model.json"
        csv_paths = tuple(sorted(path for path in files if path.name.endswith((".csv", ".csv.gz"))))
        csv_names = tuple(sorted({f"{path.name.removesuffix('.gz')}.gz" for path in csv_paths}))
        manufacturer_path = artifact_directory / "manufacturer.json"
        if model_path not in files:
            raise ProfilePreparationError("model.json is required")
        allowed = {model_path, manufacturer_path, *csv_paths}
        unexpected = sorted(path.name for path in files if path not in allowed)
        if unexpected:
            raise ProfilePreparationError(f"Unexpected artifact file(s): {', '.join(unexpected)}")

        model = self._apply_metadata(self._read_object(model_path), metadata)
        if model.get("calculation_strategy") == "lut" and not csv_paths:
            raise ProfilePreparationError("At least one .csv.gz artifact is required for LUT profiles")
        self.validator(model, self._read_object(self.model_schema_path))

        manufacturer_directory = self._resolve_manufacturer_directory(
            metadata.manufacturer,
            metadata.manufacturer_directory,
        )
        model_directory = metadata.model_id
        profile_directory = Path("profile_library") / manufacturer_directory / model_directory
        relative_files = [profile_directory / "model.json"]
        relative_files.extend(profile_directory / name for name in csv_names)
        is_new_manufacturer = not self._manufacturer_exists(manufacturer_directory)
        if is_new_manufacturer:
            relative_files.append(Path("profile_library") / manufacturer_directory / "manufacturer.json")

        self._block_collisions(relative_files)
        warnings = self._duplicate_warnings(model, manufacturer_directory, model_directory)

        return ContributionPreview(
            manufacturer_directory=manufacturer_directory,
            model_directory=model_directory,
            files=tuple(
                self._prepared_file(relative_path, artifact_directory, model, metadata)
                for relative_path in relative_files
            ),
            warnings=tuple(warnings),
        )

    def prepared_contents(
        self,
        artifact_directory: Path,
        metadata: ContributionMetadata,
        preview: ContributionPreview,
    ) -> tuple[tuple[str, bytes], ...]:
        model = self._apply_metadata(self._read_object(artifact_directory / "model.json"), metadata)
        result: list[tuple[str, bytes]] = []
        for file in preview.files:
            relative_path = Path(file.path)
            content = self._prepared_file_content(relative_path, artifact_directory, model, metadata)
            result.append((file.path, content))
        return tuple(result)

    @staticmethod
    def _apply_metadata(model: dict[str, Any], metadata: ContributionMetadata) -> dict[str, Any]:
        if metadata.product_name is not None:
            model["name"] = metadata.product_name
        model["author_info"] = {
            "name": metadata.author.name,
            "github": metadata.author.github,
            **({"email": metadata.author.email} if metadata.author.email else {}),
        }
        return model

    def _resolve_manufacturer_directory(self, manufacturer: str, requested_directory: str | None) -> str:
        requested = self._normalize(manufacturer)
        for path in sorted(self.library_root.iterdir()) if self.library_root.exists() else ():
            manifest = path / "manufacturer.json"
            if not path.is_dir() or not manifest.exists():
                continue
            data = self._read_object(manifest)
            aliases = data.get("aliases", [])
            names = [data.get("name"), *(aliases if isinstance(aliases, list) else [])]
            if requested in {self._normalize(str(name)) for name in names if name}:
                return path.name
        index_path = self.library_root / "library.json"
        if index_path.exists():
            index = self._read_object(index_path)
            manufacturers = index.get("manufacturers", [])
            if isinstance(manufacturers, list):
                for item in manufacturers:
                    if not isinstance(item, dict):
                        continue
                    aliases = item.get("aliases", [])
                    names = [item.get("name"), item.get("full_name"), *(aliases if isinstance(aliases, list) else [])]
                    if requested in {self._normalize(str(name)) for name in names if name}:
                        directory = item.get("dir_name")
                        if isinstance(directory, str) and directory:
                            return directory
        return requested_directory or self._slug(manufacturer)

    def _manufacturer_exists(self, directory: str) -> bool:
        if (self.library_root / directory).is_dir():
            return True
        index_path = self.library_root / "library.json"
        if not index_path.exists():
            return False
        index = self._read_object(index_path)
        manufacturers = index.get("manufacturers", [])
        return isinstance(manufacturers, list) and any(
            isinstance(item, dict) and item.get("dir_name") == directory for item in manufacturers
        )

    def _block_collisions(self, relative_files: list[Path]) -> None:
        for relative_path in relative_files:
            library_relative = Path(*relative_path.parts[1:])
            if (self.library_root / library_relative).exists():
                raise ProfilePreparationError(f"Refusing to overwrite existing profile path: {relative_path}")
        index_path = self.library_root / "library.json"
        if not index_path.exists():
            return
        index = self._read_object(index_path)
        # Casefolded: GitHub hosting is case-sensitive, but "LCT001" and "lct001"
        # would still be near-duplicate profiles in the library.
        existing_paths = {
            f"profile_library/{manufacturer.get('dir_name')}/{model.get('id')}/model.json".casefold()
            for manufacturer in index.get("manufacturers", [])
            if isinstance(manufacturer, dict)
            for model in manufacturer.get("models", [])
            if isinstance(model, dict)
        }
        for relative_path in relative_files:
            if relative_path.as_posix().casefold() in existing_paths:
                raise ProfilePreparationError(f"Refusing to overwrite existing profile path: {relative_path}")

    def _duplicate_warnings(
        self,
        model: dict[str, Any],
        manufacturer_directory: str,
        model_directory: str,
    ) -> list[str]:
        warnings: list[str] = []
        requested_name = self._normalize(str(model.get("name", "")))
        for model_path in self.library_root.glob("*/*/model.json"):
            if model_path.parent.parent.name == manufacturer_directory and model_path.parent.name == model_directory:
                continue
            try:
                existing = self._read_object(model_path)
            except OSError, ValueError:
                continue
            aliases = existing.get("aliases", [])
            names = [existing.get("name"), *(aliases if isinstance(aliases, list) else [])]
            if requested_name and requested_name in {self._normalize(str(name)) for name in names if name}:
                profile_path = model_path.relative_to(self.library_root)
                warnings.append(f"Possible duplicate profile: profile_library/{profile_path}")
        index_path = self.library_root / "library.json"
        if index_path.exists():
            warnings.extend(
                self._index_duplicate_warnings(
                    self._read_object(index_path),
                    requested_name,
                    manufacturer_directory,
                    model_directory,
                ),
            )
        return list(dict.fromkeys(warnings))

    def _index_duplicate_warnings(
        self,
        index: dict[str, Any],
        requested_name: str,
        manufacturer_directory: str,
        model_directory: str,
    ) -> list[str]:
        warnings: list[str] = []
        for manufacturer in index.get("manufacturers", []):
            if not isinstance(manufacturer, dict):
                continue
            for existing in manufacturer.get("models", []):
                if not isinstance(existing, dict):
                    continue
                if manufacturer.get("dir_name") == manufacturer_directory and existing.get("id") == model_directory:
                    continue
                aliases = existing.get("aliases", [])
                names = [existing.get("name"), *(aliases if isinstance(aliases, list) else [])]
                if requested_name and requested_name in {self._normalize(str(name)) for name in names if name}:
                    directory = manufacturer.get("dir_name")
                    model_id = existing.get("id")
                    warnings.append(f"Possible duplicate profile: profile_library/{directory}/{model_id}/model.json")
        return warnings

    def _prepared_file(
        self,
        relative_path: Path,
        artifact_directory: Path,
        model: dict[str, Any],
        metadata: ContributionMetadata,
    ) -> ContributionPreparedFile:
        content = self._prepared_file_content(relative_path, artifact_directory, model, metadata)
        return ContributionPreparedFile(
            path=relative_path.as_posix(),
            size=len(content),
            sha=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def _prepared_file_content(
        relative_path: Path,
        artifact_directory: Path,
        model: dict[str, Any],
        metadata: ContributionMetadata,
    ) -> bytes:
        if relative_path.name == "model.json":
            return json.dumps(model, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        if relative_path.name == "manufacturer.json":
            aliases: list[Any] = []
            artifact_manifest = artifact_directory / "manufacturer.json"
            if artifact_manifest.exists():
                with artifact_manifest.open(encoding="utf-8") as file:
                    existing = json.load(file)
                if isinstance(existing, dict) and isinstance(existing.get("aliases"), list):
                    aliases = existing["aliases"]
            payload = {"name": metadata.manufacturer, "aliases": aliases}
            return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        artifact_path = artifact_directory / relative_path.name
        if artifact_path.exists():
            return artifact_path.read_bytes()
        if relative_path.name.endswith(".csv.gz"):
            raw_path = artifact_directory / relative_path.name.removesuffix(".gz")
            if raw_path.exists():
                return gzip.compress(raw_path.read_bytes(), mtime=0)
        raise ProfilePreparationError(f"Artifact file is missing: {relative_path.name}")

    @staticmethod
    def _artifact_files(artifact_directory: Path) -> set[Path]:
        return {path for path in artifact_directory.iterdir() if path.is_file() and not path.is_symlink()}

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            raise ProfilePreparationError(f"{path.name} must contain a JSON object")
        return value

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9 ._()+-]+", "", value.casefold()).strip()
        slug = re.sub(r"\s+", " ", slug)
        if not slug:
            raise ProfilePreparationError("Manufacturer directory cannot be empty")
        return slug


def _jsonschema_validate(instance: dict[str, Any], schema: dict[str, Any]) -> None:
    from jsonschema import validate

    validate(instance=instance, schema=schema)
