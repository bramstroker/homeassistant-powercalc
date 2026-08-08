from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

COMMENT_MARKER = "<!-- model.json validate action comment -->"
PROFILE_DIRECTORY = "profile_library"


@dataclass(frozen=True)
class ProfileJson:
    """A profile library JSON file kind and where it lives inside the library."""

    file_name: str
    # Number of path parts, including the profile_library directory itself:
    # profile_library/<manufacturer>/<model>/model.json is 4, one less for manufacturer.json.
    path_length: int


MODEL_JSON = ProfileJson(file_name="model.json", path_length=4)
MANUFACTURER_JSON = ProfileJson(file_name="manufacturer.json", path_length=3)
PROFILE_JSON_KINDS = (MODEL_JSON, MANUFACTURER_JSON)


def _format_path(error: ValidationError) -> str:
    if not error.absolute_path:
        return "$"

    return "$." + ".".join(str(part) for part in error.absolute_path)


def _format_error(error: ValidationError) -> str:
    details = [
        f"- Path: `{_format_path(error)}`",
        f"- Validator: `{error.validator}`",
        f"- Message:\n\n  ```text\n  {error.message}\n  ```",
    ]

    return "\n".join(details)


def _load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _load_changed_files(path: Path) -> list[Path]:
    return [Path(filename) for filename in cast(list[str], _load_json(path))]


def _profile_json_files(changed_files: list[Path], profile_json: ProfileJson) -> list[Path]:
    return [
        path
        for path in changed_files
        if len(path.parts) == profile_json.path_length
        and path.parts[0] == PROFILE_DIRECTORY
        and path.parts[-1] == profile_json.file_name
        and path.is_file()
    ]


def _validate_files(changed_files: list[Path], schemas: dict[ProfileJson, Path]) -> dict[Path, list[ValidationError]]:
    errors_by_file: dict[Path, list[ValidationError]] = {}
    for profile_json, schema_path in schemas.items():
        validator = Draft202012Validator(cast(dict[str, object], _load_json(schema_path)))
        for path in _profile_json_files(changed_files, profile_json):
            errors = sorted(validator.iter_errors(_load_json(path)), key=lambda error: list(error.absolute_path))
            if errors:
                errors_by_file[path] = errors

    return errors_by_file


def _validated_file_names() -> str:
    return " and ".join(f"`{profile_json.file_name}`" for profile_json in PROFILE_JSON_KINDS)


def _build_report(errors_by_file: dict[Path, list[ValidationError]]) -> str:
    if not errors_by_file:
        return f"{COMMENT_MARKER}\n\nAll changed {_validated_file_names()} files are valid."

    sections = [COMMENT_MARKER, f"JSON Schema validation failed for changed {_validated_file_names()} files."]
    for path, errors in errors_by_file.items():
        sections.append(f"## `{path}`")
        sections.extend(_format_error(error) for error in errors)

    return "\n\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-schema", type=Path, required=True)
    parser.add_argument("--manufacturer-schema", type=Path, required=True)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()

    errors_by_file = _validate_files(
        _load_changed_files(args.changed_files),
        {MODEL_JSON: args.model_schema, MANUFACTURER_JSON: args.manufacturer_schema},
    )

    args.report.write_text(_build_report(errors_by_file), encoding="utf-8")
    args.status.write_text("failure" if errors_by_file else "success", encoding="utf-8")

    return 1 if errors_by_file else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
