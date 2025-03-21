import glob
import json
import os

from jsonschema import ValidationError, validate

from utils.library.common import PROFILE_DIRECTORY


def load_json(file_path: str) -> dict:
    """Load a JSON file from the given file path."""
    with open(file_path) as file:
        return json.load(file)


def validate_model(model_path: str, schema: dict) -> None:
    """Validate a JSON model against the schema."""
    try:
        model = load_json(model_path)
        validate(instance=model, schema=schema)
        print(f"VALID: {model_path}")  # noqa: T201
    except ValidationError as e:
        print(f"INVALID: {model_path}\nError: {e.message}")  # noqa: T201
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {model_path}\nError: {e}")  # noqa: T201


def validate_models_with_glob(directory: str, schema_path: str) -> None:
    """Validate model.json files up to 2 subdirectory levels using glob."""
    schema = load_json(schema_path)
    pattern = os.path.join(directory, "*/*/model.json")
    for model_path in glob.glob(pattern):
        validate_model(model_path, schema)


if __name__ == "__main__":
    schema_file_path = os.path.join(os.path.dirname(__file__), "../../profile_library/model_schema.json")

    validate_models_with_glob(PROFILE_DIRECTORY, schema_file_path)
