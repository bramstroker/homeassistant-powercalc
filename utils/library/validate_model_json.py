import glob
import json
import os
from typing import Any, cast

from jsonschema import ValidationError, validate

from utils.library.common import PROFILE_DIRECTORY

SCHEMA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../profile_library")
MODEL_GLOB = "*/*/model.json"
SUB_MODEL_GLOB = "*/*/*/model.json"
MANUFACTURER_GLOB = "*/manufacturer.json"

# Keywords of the model schema which only hold for a complete profile.
SUB_PROFILE_EXEMPT_KEYWORDS = ("required", "allOf")
# Power values a sub profile may zero out, overriding what it would inherit from its parent.
SUB_PROFILE_ZEROABLE_PROPERTIES = ("standby_power", "standby_power_on")


def load_json(file_path: str) -> dict[str, Any]:
    """Load a JSON file from the given file path."""
    with open(file_path) as file:
        return cast(dict[str, Any], json.load(file))


def sub_profile_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Derive the schema a sub profile is held to from the one for a complete profile.

    A sub profile inherits everything it does not set from its parent, so it is legitimately
    partial: `required` and the conditionals hanging off `allOf` describe the merged profile,
    not the file. Everything else still applies, `additionalProperties` above all — the
    undeclared keys the library carries today live in sub profiles.

    The one relaxed rule is the lower bound on the standby values. `0.05` keeps a complete
    profile from passing off an unmeasured `0` as a measurement, but a sub profile setting `0`
    is saying something real: this variant draws nothing on standby, unlike its parent.
    """
    properties = {
        name: {**subschema, "minimum": 0} if name in SUB_PROFILE_ZEROABLE_PROPERTIES else subschema
        for name, subschema in schema.get("properties", {}).items()
    }

    return {
        **{key: value for key, value in schema.items() if key not in SUB_PROFILE_EXEMPT_KEYWORDS},
        "properties": properties,
    }


def validate_file(file_path: str, schema: dict[str, Any]) -> bool:
    """Validate a JSON file against the schema, returning whether it passed."""
    try:
        instance = load_json(file_path)
        validate(instance=instance, schema=schema)
        print(f"VALID: {file_path}")  # noqa: T201
    except ValidationError as e:
        print(f"INVALID: {file_path}\nError: {e.message}")  # noqa: T201
        return False
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {file_path}\nError: {e}")  # noqa: T201
        return False
    return True


def validate_files_with_glob(directory: str, pattern: str, schema_path: str) -> bool:
    """Validate every JSON file matching the glob pattern against the schema."""
    return validate_files_with_schema(directory, pattern, load_json(schema_path))


def validate_files_with_schema(directory: str, pattern: str, schema: dict[str, Any]) -> bool:
    """Validate every JSON file matching the glob pattern against an already loaded schema."""
    results = [validate_file(file_path, schema) for file_path in sorted(glob.glob(os.path.join(directory, pattern)))]
    return all(results)


def validate_models_with_glob(directory: str, schema_path: str) -> bool:
    """Validate model.json files of complete profiles and of their sub profiles."""
    schema = load_json(schema_path)
    models_valid = validate_files_with_schema(directory, MODEL_GLOB, schema)
    sub_models_valid = validate_files_with_schema(directory, SUB_MODEL_GLOB, sub_profile_schema(schema))
    return models_valid and sub_models_valid


def validate_manufacturers_with_glob(directory: str, schema_path: str) -> bool:
    """Validate manufacturer.json files 1 subdirectory level deep using glob."""
    return validate_files_with_glob(directory, MANUFACTURER_GLOB, schema_path)


def main() -> int:
    """Validate the whole library, returning a process exit code."""
    manufacturers_valid = validate_manufacturers_with_glob(
        PROFILE_DIRECTORY,
        os.path.join(SCHEMA_DIRECTORY, "manufacturer_schema.json"),
    )
    models_valid = validate_models_with_glob(PROFILE_DIRECTORY, os.path.join(SCHEMA_DIRECTORY, "model_schema.json"))

    return 0 if manufacturers_valid and models_valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
