from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from measure.contribution.models import ContributionPreparedFile, ContributionPreview
from measure.model import mains_voltage_from_range
from measure.profile.models import ProfileMetadata

JsonValidator = Callable[[dict[str, Any], dict[str, Any]], None]

MODEL_JSON = "model.json"
MANUFACTURER_JSON = "manufacturer.json"
LIBRARY_URL = "https://library.powercalc.nl"
EMPTY_OPTIONAL_MODEL_FIELDS = (
    "aliases",
    "ean",
    "product_url",
    "device_specs",
    "measure_device_firmware",
    "measure_description",
)


class ProfilePreparationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class ManufacturerResolution:
    directory: str
    #: Only the manufacturer's own name(s), never its aliases: aliases are commonly
    #: sub-brands or product lines ("FRITZ!", "Tapo", "Kasa") that legitimately start
    #: a product name, so they must not be rejected as a repeated manufacturer.
    primary_names: frozenset[str]
    exists: bool

    @property
    def library_url(self) -> str | None:
        if not self.exists:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", self.directory.casefold()).strip("-")
        return f"{LIBRARY_URL}/manufacturers/{slug}" if slug else None


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

    def prepare(self, artifact_directory: Path, metadata: ProfileMetadata) -> ContributionPreview:
        artifact_directory = artifact_directory.resolve()
        csv_names = self._artifact_csv_names(artifact_directory)
        model = self._apply_metadata(self._read_object(artifact_directory / MODEL_JSON), metadata)
        if not str(model.get("name") or "").strip():
            raise ProfilePreparationError("Enter the product name", field="product_name")
        if "mains_voltage" not in model:
            raise ProfilePreparationError(
                "Select the nominal mains voltage because no voltage range was measured",
                field="mains_voltage",
            )
        if model["mains_voltage"] not in (120, 230):
            raise ProfilePreparationError(
                "Nominal mains voltage must be either 120 or 230",
                field="mains_voltage",
            )
        manufacturer = self._resolve_manufacturer(metadata.manufacturer)
        self._validate_product_name(str(model.get("name", "")), metadata.manufacturer, manufacturer.primary_names)
        if model.get("calculation_strategy") == "lut" and not csv_names:
            raise ProfilePreparationError("At least one .csv.gz artifact is required for LUT profiles")
        self.validator(model, self._read_object(self.model_schema_path))

        manufacturer_directory = manufacturer.directory
        profile_directory = Path("profile_library") / manufacturer_directory / metadata.model_id
        relative_files = [profile_directory / name for name in (MODEL_JSON, *csv_names)]
        if not manufacturer.exists:
            relative_files.append(profile_directory.parent / MANUFACTURER_JSON)
        self._block_collisions(relative_files)

        return ContributionPreview(
            manufacturer_directory=manufacturer_directory,
            manufacturer_library_url=manufacturer.library_url,
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
        metadata: ProfileMetadata,
        preview: ContributionPreview,
    ) -> tuple[tuple[str, bytes], ...]:
        model = self._apply_metadata(self._read_object(artifact_directory / MODEL_JSON), metadata)
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
        if MODEL_JSON not in names:
            raise ProfilePreparationError("model.json is required")
        csv_names = {name for name in names if name.endswith((".csv", ".csv.gz"))}
        unexpected = sorted(names - csv_names - {MODEL_JSON, MANUFACTURER_JSON})
        if unexpected:
            raise ProfilePreparationError(f"Unexpected artifact file(s): {', '.join(unexpected)}")
        return tuple(sorted({f"{name.removesuffix('.gz')}.gz" for name in csv_names}))

    @staticmethod
    def _apply_metadata(model: dict[str, Any], metadata: ProfileMetadata) -> dict[str, Any]:
        if metadata.product_name is not None:
            model["name"] = metadata.product_name
        optional_values: tuple[tuple[str, Any], ...] = (
            ("aliases", list(metadata.aliases) if metadata.aliases is not None else None),
            ("ean", list(metadata.gtins) if metadata.gtins is not None else None),
            ("product_url", metadata.product_url),
            ("mains_voltage", metadata.mains_voltage),
            ("device_specs", metadata.device_specs),
            ("measure_device", metadata.measure_device),
            ("measure_device_firmware", metadata.measure_device_firmware),
            ("measure_description", metadata.measure_description),
        )
        model.update({key: value for key, value in optional_values if value is not None})
        derived_mains_voltage = mains_voltage_from_range(model.get("voltage_range"))
        if derived_mains_voltage is not None:
            model["mains_voltage"] = derived_mains_voltage
        if metadata.author is not None:
            model["authors"] = [
                {
                    "name": metadata.author.name,
                    "github": metadata.author.github,
                    **({"email": metadata.author.email} if metadata.author.email else {}),
                },
            ]
        for key in EMPTY_OPTIONAL_MODEL_FIELDS:
            value = model.get(key)
            if _is_empty_optional_value(value):
                model.pop(key, None)
        return model

    def _resolve_manufacturer(self, manufacturer: str) -> ManufacturerResolution:
        requested = self._normalize(manufacturer)
        for directory, manifest in self._manufacturer_manifests():
            if requested in self._known_names(manifest, "name"):
                return ManufacturerResolution(
                    directory=directory,
                    primary_names=frozenset(self._name_values(manifest, "name")),
                    exists=True,
                )
        for entry in self._manufacturers_in_index():
            dir_name = entry.get("dir_name")
            if isinstance(dir_name, str) and dir_name and requested in self._known_names(entry, "name", "full_name"):
                return ManufacturerResolution(
                    directory=dir_name,
                    primary_names=frozenset(self._name_values(entry, "name", "full_name")),
                    exists=True,
                )
        directory = self._slugify(manufacturer)
        return ManufacturerResolution(
            directory=directory,
            primary_names=frozenset({manufacturer}),
            # The entered name matched nothing, but its derived directory may still
            # exist. Never overwrite an upstream manifest in that case.
            exists=self._manufacturer_directory_exists(directory),
        )

    def _manufacturer_directory_exists(self, directory: str) -> bool:
        """Whether ``directory`` is already a manufacturer in the checkout or the index."""
        return (self.library_root / directory).is_dir() or any(
            entry.get("dir_name") == directory for entry in self._manufacturers_in_index()
        )

    @classmethod
    def _validate_product_name(cls, product_name: str, entered_manufacturer: str, known_names: frozenset[str]) -> None:
        normalized_product = cls._normalize_words(product_name)
        manufacturer_names = {cls._normalize_words(name) for name in (*known_names, entered_manufacturer)}
        repeated = next(
            (
                name
                for name in sorted(manufacturer_names, key=len, reverse=True)
                if name and (normalized_product == name or normalized_product.startswith(f"{name} "))
            ),
            None,
        )
        if repeated is not None:
            raise ProfilePreparationError(
                "Product name must not start with the manufacturer; enter only the marketed model name",
                field="product_name",
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
        return {cls._normalize(name) for name in cls._known_name_values(entry, *keys)}

    @classmethod
    def _known_name_values(cls, entry: dict[str, Any], *keys: str) -> set[str]:
        aliases = entry.get("aliases")
        return cls._name_values(entry, *keys) | (
            {str(alias).strip() for alias in aliases if alias and str(alias).strip()}
            if isinstance(aliases, list)
            else set()
        )

    @staticmethod
    def _name_values(entry: dict[str, Any], *keys: str) -> set[str]:
        """The entry's own name(s) under ``keys``, without its aliases."""
        return {str(entry[key]).strip() for key in keys if entry.get(key) and str(entry[key]).strip()}

    def _build_prepared_file(
        self,
        relative_path: Path,
        artifact_directory: Path,
        model: dict[str, Any],
        metadata: ProfileMetadata,
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
        metadata: ProfileMetadata,
    ) -> bytes:
        if relative_path.name == MODEL_JSON:
            return _dump_json(model)
        if relative_path.name == MANUFACTURER_JSON:
            return _dump_json({"name": metadata.manufacturer, "aliases": self._artifact_aliases(artifact_directory)})
        artifact_path = artifact_directory / relative_path.name
        if artifact_path.exists():
            return artifact_path.read_bytes()
        raw_path = artifact_directory / relative_path.name.removesuffix(".gz")
        if relative_path.name.endswith(".csv.gz") and raw_path.exists():
            return gzip.compress(raw_path.read_bytes(), mtime=0)
        raise ProfilePreparationError(f"Artifact file is missing: {relative_path.name}")

    def _artifact_aliases(self, artifact_directory: Path) -> list[Any]:
        manifest = artifact_directory / MANUFACTURER_JSON
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
    def _normalize_words(value: str) -> str:
        return re.sub(r"[\W_]+", " ", value.casefold()).strip()

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9 ._()+-]+", "", value.casefold()).strip()
        slug = re.sub(r"\s+", " ", slug)
        if not slug:
            raise ProfilePreparationError("Manufacturer directory cannot be empty")
        return slug


def _is_empty_optional_value(value: object) -> bool:
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or (isinstance(value, (list, dict)) and not value)
    )


def _dump_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _jsonschema_validate(instance: dict[str, Any], schema: dict[str, Any]) -> None:
    from jsonschema import SchemaError, ValidationError, validate

    try:
        validate(instance=instance, schema=schema)
    except ValidationError as error:
        from jsonschema.exceptions import best_match

        error = best_match(error.context) or error
        location = ".".join(str(part) for part in error.absolute_path)
        location_suffix = f" at {location}" if location else ""
        field = _schema_error_field(tuple(error.absolute_path))
        raise ProfilePreparationError(
            f"model.json does not match model_schema.json{location_suffix}: {error.message}",
            field=field,
        ) from error
    except SchemaError as error:
        raise ProfilePreparationError(f"model_schema.json is invalid: {error.message}") from error


def _schema_error_field(path: tuple[str | int, ...]) -> str | None:
    """Translate generated model paths to editable form fields (not array indices)."""
    if not path:
        return None
    root = str(path[0])
    if root == "authors" and len(path) >= 3:
        return {"name": "contributor", "github": "contributor_github", "email": "contributor_email"}.get(str(path[2]))
    if root == "device_specs":
        return ".".join(str(part) for part in path[:2])
    return {"name": "product_name", "ean": "gtins"}.get(root, root)
