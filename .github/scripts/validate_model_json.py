from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

COMMENT_MARKER = "<!-- model.json validate action comment -->"


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


def _model_json_files(changed_files: list[Path]) -> list[Path]:
    return [
        path
        for path in changed_files
        if len(path.parts) == 4
        and path.parts[0] == "profile_library"
        and path.parts[-1] == "model.json"
        and path.is_file()
    ]


def _build_report(errors_by_file: dict[Path, list[ValidationError]]) -> str:
    if not errors_by_file:
        return f"{COMMENT_MARKER}\n\nAll changed `model.json` files are valid."

    sections = [COMMENT_MARKER, "JSON Schema validation failed for changed `model.json` files."]
    for path, errors in errors_by_file.items():
        sections.append(f"## `{path}`")
        sections.extend(_format_error(error) for error in errors)

    return "\n\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()

    schema = cast(dict[str, object], _load_json(args.schema))
    validator = Draft202012Validator(schema)
    errors_by_file: dict[Path, list[ValidationError]] = {}

    for model_path in _model_json_files(_load_changed_files(args.changed_files)):
        instance = _load_json(model_path)
        errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
        if errors:
            errors_by_file[model_path] = errors

    args.report.write_text(_build_report(errors_by_file), encoding="utf-8")
    args.status.write_text("failure" if errors_by_file else "success", encoding="utf-8")

    return 1 if errors_by_file else 0


if __name__ == "__main__":
    raise SystemExit(main())
