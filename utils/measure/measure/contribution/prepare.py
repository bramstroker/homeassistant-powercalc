from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
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
    """Prepare generated profile artifacts for a profile-library pull request.

    ``library_root`` is either a full checkout of the profile library (directories
    with ``manufacturer.json``/``model.json``) or a sparse download that only holds
    ``library.json``. Manufacturer resolution, collision and duplicate checks
    therefore consult both the directory tree and the index.
    """

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
        csv_names = self._artifact_csv_names(artifact_directory)
        model = self._apply_metadata(self._read_object(artifact_directory / "model.json"), metadata)
        if model.get("calculation_strategy") == "lut" and not csv_names:
            raise ProfilePreparationError("At least one .csv.gz artifact is required for LUT profiles")
        self.validator(model, self._read_object(self.model_schema_path))

        manufacturer_directory = self._resolve_manufacturer_directory(
            metadata.manufacturer,
            metadata.manufacturer_directory,
        )
        profile_directory = Path("profile_library") / manufacturer_directory / metadata.model_id
        relative_files = [profile_directory / name for name in ("model.json", *csv_names)]
        if not self._manufacturer_exists(manufacturer_directory):
            relative_files.append(profile_directory.parent / "manufacturer.json")
        self._block_collisions(relative_files)

        return ContributionPreview(
            manufacturer_directory=manufacturer_directory,
            model_directory=metadata.model_id,
            files=tuple(
                self._build_prepared_file(relative_path, artifact_directory, model, metadata)
                for relative_path in relative_files
            ),
            warnings=self._collect_duplicate_warnings(model, manufacturer_directory, metadata.model_id),
        )

    def render_contents(
        self,
        artifact_directory: Path,
        metadata: ContributionMetadata,
        preview: ContributionPreview,
    ) -> tuple[tuple[str, bytes], ...]:
        model = self._apply_metadata(self._read_object(artifact_directory / "model.json"), metadata)
        return tuple(
            (file.path, self._render_file_content(Path(file.path), artifact_directory, model, metadata))
            for file in preview.files
        )

    @staticmethod
    def _artifact_csv_names(artifact_directory: Path) -> tuple[str, ...]:
        """Validate the artifact directory layout and return the gzipped CSV file names."""
        if not artifact_directory.is_dir():
            raise ProfilePreparationError("Artifact directory does not exist")
        names = {path.name for path in artifact_directory.iterdir() if path.is_file() and not path.is_symlink()}
        if "model.json" not in names:
            raise ProfilePreparationError("model.json is required")
        csv_names = {name for name in names if name.endswith((".csv", ".csv.gz"))}
        unexpected = sorted(names - csv_names - {"model.json", "manufacturer.json"})
        if unexpected:
            raise ProfilePreparationError(f"Unexpected artifact file(s): {', '.join(unexpected)}")
        return tuple(sorted({f"{name.removesuffix('.gz')}.gz" for name in csv_names}))

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
        for directory, manifest in self._manufacturer_manifests():
            if requested in self._known_names(manifest, "name"):
                return directory
        for entry in self._manufacturers_in_index():
            dir_name = entry.get("dir_name")
            if isinstance(dir_name, str) and dir_name and requested in self._known_names(entry, "name", "full_name"):
                return dir_name
        return requested_directory or self._slugify(manufacturer)

    def _manufacturer_exists(self, directory: str) -> bool:
        return (self.library_root / directory).is_dir() or any(
            entry.get("dir_name") == directory for entry in self._manufacturers_in_index()
        )

    def _block_collisions(self, relative_files: Sequence[Path]) -> None:
        # Casefolded: GitHub hosting is case-sensitive, but "LCT001" and "lct001"
        # would still be near-duplicate profiles in the library.
        indexed_paths = {
            f"profile_library/{directory}/{model.get('id')}/model.json".casefold()
            for directory, model in self._models_in_index()
        }
        for relative_path in relative_files:
            in_library = (self.library_root / Path(*relative_path.parts[1:])).exists()
            if in_library or relative_path.as_posix().casefold() in indexed_paths:
                raise ProfilePreparationError(f"Refusing to overwrite existing profile path: {relative_path}")

    def _collect_duplicate_warnings(
        self,
        model: dict[str, Any],
        manufacturer_directory: str,
        model_directory: str,
    ) -> tuple[str, ...]:
        requested_name = self._normalize(str(model.get("name", "")))
        if not requested_name:
            return ()
        warnings: list[str] = []
        for model_path in self.library_root.glob("*/*/model.json"):
            if model_path.parent.parent.name == manufacturer_directory and model_path.parent.name == model_directory:
                continue
            try:
                existing = self._read_object(model_path)
            except OSError, ValueError:
                continue
            if requested_name in self._known_names(existing, "name"):
                relative = model_path.relative_to(self.library_root)
                warnings.append(f"Possible duplicate profile: profile_library/{relative}")
        for directory, existing in self._models_in_index():
            if directory == manufacturer_directory and existing.get("id") == model_directory:
                continue
            if requested_name in self._known_names(existing, "name"):
                path = f"{directory}/{existing.get('id')}/model.json"
                warnings.append(f"Possible duplicate profile: profile_library/{path}")
        return tuple(dict.fromkeys(warnings))

    def _manufacturer_manifests(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield (directory name, manifest) for each manufacturer in a full library checkout."""
        if not self.library_root.exists():
            return
        for path in sorted(self.library_root.iterdir()):
            manifest = path / "manufacturer.json"
            if path.is_dir() and manifest.exists():
                yield path.name, self._read_object(manifest)

    def _manufacturers_in_index(self) -> list[dict[str, Any]]:
        """Manufacturer entries from the downloaded ``library.json``, if present."""
        index_path = self.library_root / "library.json"
        if not index_path.exists():
            return []
        manufacturers = self._read_object(index_path).get("manufacturers")
        if not isinstance(manufacturers, list):
            return []
        return [entry for entry in manufacturers if isinstance(entry, dict)]

    def _models_in_index(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield (manufacturer directory, model entry) pairs from ``library.json``."""
        for manufacturer in self._manufacturers_in_index():
            directory = manufacturer.get("dir_name")
            models = manufacturer.get("models")
            if not isinstance(directory, str) or not isinstance(models, list):
                continue
            for model in models:
                if isinstance(model, dict):
                    yield directory, model

    @classmethod
    def _known_names(cls, entry: dict[str, Any], *keys: str) -> set[str]:
        """All normalized names an entry answers to: the values of ``keys`` plus its aliases."""
        names = [entry.get(key) for key in keys]
        aliases = entry.get("aliases")
        if isinstance(aliases, list):
            names.extend(aliases)
        return {cls._normalize(str(name)) for name in names if name}

    def _build_prepared_file(
        self,
        relative_path: Path,
        artifact_directory: Path,
        model: dict[str, Any],
        metadata: ContributionMetadata,
    ) -> ContributionPreparedFile:
        content = self._render_file_content(relative_path, artifact_directory, model, metadata)
        return ContributionPreparedFile(
            path=relative_path.as_posix(),
            size=len(content),
            sha=hashlib.sha256(content).hexdigest(),
        )

    def _render_file_content(
        self,
        relative_path: Path,
        artifact_directory: Path,
        model: dict[str, Any],
        metadata: ContributionMetadata,
    ) -> bytes:
        if relative_path.name == "model.json":
            return _dump_json(model)
        if relative_path.name == "manufacturer.json":
            return _dump_json({"name": metadata.manufacturer, "aliases": self._artifact_aliases(artifact_directory)})
        artifact_path = artifact_directory / relative_path.name
        if artifact_path.exists():
            return artifact_path.read_bytes()
        raw_path = artifact_directory / relative_path.name.removesuffix(".gz")
        if relative_path.name.endswith(".csv.gz") and raw_path.exists():
            return gzip.compress(raw_path.read_bytes(), mtime=0)
        raise ProfilePreparationError(f"Artifact file is missing: {relative_path.name}")

    def _artifact_aliases(self, artifact_directory: Path) -> list[Any]:
        manifest = artifact_directory / "manufacturer.json"
        if not manifest.exists():
            return []
        aliases = self._read_object(manifest).get("aliases")
        return aliases if isinstance(aliases, list) else []

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
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9 ._()+-]+", "", value.casefold()).strip()
        slug = re.sub(r"\s+", " ", slug)
        if not slug:
            raise ProfilePreparationError("Manufacturer directory cannot be empty")
        return slug


def _dump_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _jsonschema_validate(instance: dict[str, Any], schema: dict[str, Any]) -> None:
    from jsonschema import validate

    validate(instance=instance, schema=schema)
