"""Prepare measured artifacts for the Powercalc profile library."""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

from pydantic import ValidationError

from measure.const import PROJECT_DIR
from measure.contribution.models import ContributionPreview
from measure.contribution.prepare import ProfilePreparationError, ProfilePreparer
from measure.model import mains_voltage_from_range
from measure.profile.models import ProfileMetadata
from measure.profile.output import write_prepared_profile
from measure.profile.specifications import DeviceSpecField, device_spec_fields

Prompt = Callable[[str], str]


@dataclass(frozen=True)
class ProfilePreparationRun:
    output_directory: Path
    preview: ContributionPreview


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="powercalc-profile",
        description="Enrich and validate raw Powercalc measurement artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="create a profile-library package")
    prepare.add_argument("artifact_directory", type=Path, help="directory containing model.json and measurement CSVs")
    prepare.add_argument("--metadata", type=Path, help="JSON file with profile metadata and form defaults")
    prepare.add_argument(
        "--non-interactive",
        action="store_true",
        help="do not prompt; require metadata needed beyond the generated model.json",
    )
    prepare.add_argument(
        "--library-root",
        type=Path,
        help="profile_library directory or repository checkout used for validation",
    )
    prepare.add_argument("--schema", type=Path, help="model schema path (defaults to <library-root>/model_schema.json)")
    prepare.add_argument(
        "--output",
        type=Path,
        help="output root (defaults to <artifact-directory>/prepared)",
    )
    return parser


def prepare_profile(argv: Sequence[str], *, prompt: Prompt = input) -> ProfilePreparationRun:
    args = build_parser().parse_args(argv)
    if args.command != "prepare":  # pragma: no cover - argparse enforces this
        raise ProfilePreparationError(f"Unsupported command: {args.command}")

    artifact_directory = args.artifact_directory.resolve()
    raw_model = _read_json_object(artifact_directory / "model.json")
    supplied = _read_json_object(args.metadata.resolve()) if args.metadata else {}
    unsupported = {"manufacturer_directory"} & supplied.keys()
    if unsupported:
        raise ProfilePreparationError(
            f"Unsupported metadata field: {min(unsupported)}",
            field="manufacturer",
        )
    metadata_values = _metadata_defaults(artifact_directory, raw_model)
    metadata_values.update(supplied)

    library_root = _resolve_library_root(args.library_root)
    schema_path = args.schema.resolve() if args.schema else library_root / "model_schema.json"
    if not schema_path.is_file():
        raise ProfilePreparationError(f"Model schema does not exist: {schema_path}")
    if not args.non_interactive:
        schema = _read_json_object(schema_path)
        device_type = raw_model.get("device_type")
        fields = device_spec_fields(schema).get(device_type, ()) if isinstance(device_type, str) else ()
        metadata_values = _prompt_metadata(
            metadata_values,
            prompt,
            fields,
            has_voltage_range=mains_voltage_from_range(raw_model.get("voltage_range")) is not None,
        )

    try:
        metadata = ProfileMetadata.model_validate(metadata_values)
    except ValidationError as error:
        raise ProfilePreparationError(_format_validation_error(error)) from error
    if metadata.author is None:
        raise ProfilePreparationError("Contributor name and GitHub username are required")

    output_directory = (args.output or artifact_directory / "prepared").resolve()
    preview = write_prepared_profile(
        preparer=ProfilePreparer(library_root=library_root, model_schema_path=schema_path),
        artifact_directory=artifact_directory,
        metadata=metadata,
        output_directory=output_directory,
    )
    return ProfilePreparationRun(output_directory=output_directory, preview=preview)


def _metadata_defaults(artifact_directory: Path, model: dict[str, Any]) -> dict[str, Any]:
    mains_voltage = model.get("mains_voltage")
    generated_directory = re.fullmatch(r"session-[0-9a-f]{32}|measurement", artifact_directory.name)
    values: dict[str, Any] = {
        "model_id": "" if generated_directory else artifact_directory.name,
        "product_name": model.get("name"),
        "measure_device": model.get("measure_device"),
        "measure_device_firmware": model.get("measure_device_firmware"),
        "measure_description": model.get("measure_description"),
        "aliases": model.get("aliases"),
        "gtins": model.get("ean"),
        "product_url": model.get("product_url"),
        "mains_voltage": mains_voltage if mains_voltage in (120, 230) else None,
        "device_specs": model.get("device_specs"),
    }
    authors = model.get("authors")
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        values["author"] = authors[0]
    return {key: value for key, value in values.items() if value is not None}


def _prompt_metadata(
    values: dict[str, Any],
    prompt: Prompt,
    device_specification_fields: tuple[DeviceSpecField, ...] = (),
    *,
    has_voltage_range: bool = False,
) -> dict[str, Any]:
    print("\nPrepare profile metadata (press Enter to keep the value in brackets).")
    result = dict(values)
    result["manufacturer"] = _ask(prompt, "Manufacturer", values.get("manufacturer"), required=True)
    result["model_id"] = _ask(prompt, "Model ID", values.get("model_id"), required=True)
    result["product_name"] = _ask(
        prompt,
        "Product name (without manufacturer)",
        values.get("product_name"),
        required=True,
    )
    result["aliases"] = _split_list(_ask(prompt, "Aliases (comma separated)", _join_list(values.get("aliases"))))
    result["gtins"] = _split_list(_ask(prompt, "GTIN/barcodes (comma separated)", _join_list(values.get("gtins"))))
    result["product_url"] = _ask(prompt, "Manufacturer product URL", values.get("product_url"))
    if not has_voltage_range:
        result["mains_voltage"] = _ask_mains_voltage(prompt, values.get("mains_voltage"))
    result["device_specs"] = _prompt_device_specs(
        prompt,
        device_specification_fields,
        values.get("device_specs"),
    )
    result["measure_device"] = _ask(prompt, "Measurement device", values.get("measure_device"))
    result["measure_device_firmware"] = _ask(
        prompt,
        "Measurement device firmware",
        values.get("measure_device_firmware"),
    )
    result["measure_description"] = _ask(
        prompt,
        "Measurement description",
        values.get("measure_description"),
    )

    author_value = values.get("author")
    author: dict[str, Any] = author_value if isinstance(author_value, dict) else {}
    result["author"] = {
        "name": _ask(prompt, "Contributor name", author.get("name"), required=True),
        "github": _ask(prompt, "Contributor GitHub username", author.get("github"), required=True),
        "email": _ask(prompt, "Contributor email", author.get("email")),
    }
    return result


def _ask_mains_voltage(prompt: Prompt, default: object) -> int:
    choices = (120, 230)
    while True:
        value = _ask(prompt, f"Nominal mains voltage ({'/'.join(map(str, choices))})", default, required=True)
        try:
            mains_voltage = int(value or "")
        except ValueError:
            mains_voltage = 0
        if mains_voltage in choices:
            return mains_voltage
        print(f"Nominal mains voltage must be one of {', '.join(map(str, choices))}.")


def _ask(prompt: Prompt, label: str, default: object = None, *, required: bool = False) -> str | None:
    default_text = str(default).strip() if default is not None else ""
    suffix = f" [{default_text}]" if default_text else ""
    while True:
        answer = prompt(f"{label}{suffix}: ").strip()
        value = answer or default_text
        if value or not required:
            return value or None
        print(f"{label} is required.")


def _prompt_device_specs(
    prompt: Prompt,
    fields: tuple[DeviceSpecField, ...],
    defaults: object,
) -> dict[str, Any] | None:
    existing = defaults if isinstance(defaults, dict) else {}
    if not fields:
        return existing or None
    print("\nDevice specifications from model_schema.json (leave blank when unknown).")
    # Specifications the current schema no longer describes are kept as they are, so editing
    # an older profile never silently drops metadata its model.json already carries.
    prompted = {field.name for field in fields}
    result: dict[str, Any] = {key: value for key, value in existing.items() if key not in prompted}
    for field in fields:
        value = _prompt_device_specification(prompt, field, existing.get(field.name))
        if value is not None:
            result[field.name] = value
    return result or None


def _prompt_device_specification(prompt: Prompt, field: DeviceSpecField, default: object) -> object:
    label = f"{field.label} ({', '.join(field.options)})" if field.options else field.label
    if field.collection != "scalar":
        return _prompt_specification_list(prompt, label, field, default)
    if field.value_type == "boolean":
        return _ask_boolean(prompt, label, default)
    if field.value_type in {"number", "integer"}:
        return _ask_number(prompt, label, default, integer=field.value_type == "integer")
    return _ask_valid_options(prompt, label, default, field)


def _prompt_specification_list(prompt: Prompt, label: str, field: DeviceSpecField, default: object) -> object:
    default_value = _join_list(default) or (str(default) if default else None)
    while True:
        values = _specification_values(_split_list(_ask_valid_options(prompt, label, default_value, field)), field)
        if values is None:
            print(f"{field.label} must be a comma separated list of numbers.")
            continue
        if field.collection == "scalar_or_array" and len(values) == 1:
            return values[0]
        return values or None


def _specification_values(values: list[str], field: DeviceSpecField) -> list[Any] | None:
    """Convert entered text to the JSON type the schema declares, or None when it does not fit."""
    if field.value_type not in {"number", "integer"}:
        return list(values)
    try:
        return [int(value) if field.value_type == "integer" else float(value) for value in values]
    except ValueError:
        return None


def _ask_valid_options(prompt: Prompt, label: str, default: object, field: DeviceSpecField) -> str | None:
    while True:
        value = _ask(prompt, label, default)
        values = _split_list(value) if field.collection != "scalar" else ([value] if value else [])
        invalid = next((item for item in values if field.options and item not in field.options), None)
        if invalid is None:
            return value
        print(f"{invalid} is not an allowed value for {field.label}.")


def _ask_boolean(prompt: Prompt, label: str, default: object) -> bool | None:
    default_text = "yes" if default is True else "no" if default is False else None
    while True:
        value = _ask(prompt, f"{label} (yes/no)", default_text)
        if value is None:
            return None
        normalized = value.casefold()
        if normalized in {"yes", "y", "true"}:
            return True
        if normalized in {"no", "n", "false"}:
            return False
        print(f"{label} must be yes or no.")


def _ask_number(prompt: Prompt, label: str, default: object, *, integer: bool) -> int | float | None:
    while True:
        value = _ask(prompt, label, default)
        if value is None:
            return None
        try:
            return int(value) if integer else float(value)
        except ValueError:
            print(f"{label} must be a {'whole number' if integer else 'number'}.")


def _join_list(value: object) -> str | None:
    if not isinstance(value, list | tuple):
        return None
    return ", ".join(str(item) for item in value)


def _split_list(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def _resolve_library_root(configured: Path | None) -> Path:
    candidate = configured.resolve() if configured else PROJECT_DIR.parents[1] / "profile_library"
    nested = candidate / "profile_library"
    if not (candidate / "model_schema.json").is_file() and (nested / "model_schema.json").is_file():
        candidate = nested
    if not candidate.is_dir():
        raise ProfilePreparationError(
            "Profile library checkout was not found; pass --library-root /path/to/profile_library",
        )
    return candidate


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
    except FileNotFoundError as error:
        raise ProfilePreparationError(f"File does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ProfilePreparationError(f"Invalid JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ProfilePreparationError(f"{path} must contain a JSON object")
    return value


def _format_validation_error(error: ValidationError) -> str:
    issue = error.errors(include_url=False)[0]
    field = ".".join(str(part) for part in issue["loc"])
    return f"Invalid {field}: {issue['msg']}" if field else str(issue["msg"])


def main() -> None:
    try:
        result = prepare_profile(sys.argv[1:])
    except (OSError, ProfilePreparationError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    print(f"\nPrepared profile written to {result.output_directory}")
    for prepared_file in result.preview.files:
        print(f"  {prepared_file.path}")
    for warning in result.preview.warnings:
        print(f"Warning: {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()
