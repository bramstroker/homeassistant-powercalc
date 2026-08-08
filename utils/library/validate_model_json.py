import glob
import json
import os
from typing import Any, cast

from jsonschema import ValidationError, validate

from utils.library.common import PROFILE_DIRECTORY

SCHEMA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../profile_library")
MODEL_GLOB = "*/*/model.json"
MANUFACTURER_GLOB = "*/manufacturer.json"


def load_json(file_path: str) -> dict[str, Any]:
    """Load a JSON file from the given file path."""
    with open(file_path) as file:
        return cast(dict[str, Any], json.load(file))


def validate_file(file_path: str, schema: dict[str, Any]) -> None:
    """Validate a JSON file against the schema."""
    try:
        instance = load_json(file_path)
        validate(instance=instance, schema=schema)
        print(f"VALID: {file_path}")  # noqa: T201
    except ValidationError as e:
        print(f"INVALID: {file_path}\nError: {e.message}")  # noqa: T201
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {file_path}\nError: {e}")  # noqa: T201


def validate_files_with_glob(directory: str, pattern: str, schema_path: str) -> None:
    """Validate every JSON file matching the glob pattern against the schema."""
    schema = load_json(schema_path)
    for file_path in sorted(glob.glob(os.path.join(directory, pattern))):
        validate_file(file_path, schema)


def validate_models_with_glob(directory: str, schema_path: str) -> None:
    """Validate model.json files up to 2 subdirectory levels using glob."""
    validate_files_with_glob(directory, MODEL_GLOB, schema_path)


def validate_manufacturers_with_glob(directory: str, schema_path: str) -> None:
    """Validate manufacturer.json files 1 subdirectory level deep using glob."""
    validate_files_with_glob(directory, MANUFACTURER_GLOB, schema_path)


def main() -> None:
    validate_manufacturers_with_glob(
        PROFILE_DIRECTORY,
        os.path.join(SCHEMA_DIRECTORY, "manufacturer_schema.json"),
    )
    validate_models_with_glob(PROFILE_DIRECTORY, os.path.join(SCHEMA_DIRECTORY, "model_schema.json"))


if __name__ == "__main__":  # pragma: no cover
    main()
