"""Behavioural tests for the profile JSON schema validation entry point.

The entry point resolves the changed files relative to the working directory, so every
test builds a miniature profile library in a temporary directory and runs from there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import validate_model_json as entry

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MODEL_SCHEMA = REPOSITORY_ROOT / "profile_library" / "model_schema.json"
MANUFACTURER_SCHEMA = REPOSITORY_ROOT / "profile_library" / "manufacturer_schema.json"

VALID_MODEL = {
    "name": "Hue White and Color Ambiance",
    "device_type": "light",
    "calculation_strategy": "lut",
    "measure_method": "script",
    "measure_device": "Shelly PM Mini Gen3",
    "created_at": "2024-12-20T00:55:44Z",
    "standby_power": 0.4,
}
VALID_MANUFACTURER = {"name": "signify", "full_name": "Signify", "aliases": ["Philips"]}


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_files: list[str],
    *,
    model_schema: Path = MODEL_SCHEMA,
    manufacturer_schema: Path = MANUFACTURER_SCHEMA,
) -> tuple[int, str, str]:
    """Run the entry point in tmp_path and return its exit code, report and status."""
    write_json(tmp_path / "changed_files.json", changed_files)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_model_json.py",
            "--model-schema",
            str(model_schema),
            "--manufacturer-schema",
            str(manufacturer_schema),
            "--changed-files",
            "changed_files.json",
            "--report",
            "report.md",
            "--status",
            "status.txt",
        ],
    )

    exit_code = entry.main()

    return (
        exit_code,
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        (tmp_path / "status.txt").read_text(encoding="utf-8"),
    )


def test_valid_model_and_manufacturer_json_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_json(tmp_path / "profile_library" / "signify" / "manufacturer.json", VALID_MANUFACTURER)
    write_json(tmp_path / "profile_library" / "signify" / "LCT010" / "model.json", VALID_MODEL)

    exit_code, report, status = run(
        tmp_path,
        monkeypatch,
        ["profile_library/signify/manufacturer.json", "profile_library/signify/LCT010/model.json"],
    )

    assert exit_code == 0
    assert status == "success"
    assert report == f"{entry.COMMENT_MARKER}\n\nAll changed `model.json` and `manufacturer.json` files are valid."


def test_invalid_manufacturer_json_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_json(tmp_path / "profile_library" / "signify" / "manufacturer.json", {"aliases": "Philips"})

    exit_code, report, status = run(tmp_path, monkeypatch, ["profile_library/signify/manufacturer.json"])

    assert exit_code == 1
    assert status == "failure"
    assert entry.COMMENT_MARKER in report
    assert "JSON Schema validation failed for changed `model.json` and `manufacturer.json` files." in report
    assert "## `profile_library/signify/manufacturer.json`" in report
    assert "- Path: `$`" in report
    assert "- Validator: `required`" in report
    assert "- Path: `$.aliases`" in report
    assert "- Validator: `type`" in report


def test_invalid_model_json_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_json(
        tmp_path / "profile_library" / "signify" / "LCT010" / "model.json",
        {**VALID_MODEL, "device_type": "toaster"},
    )

    exit_code, report, status = run(tmp_path, monkeypatch, ["profile_library/signify/LCT010/model.json"])

    assert exit_code == 1
    assert status == "failure"
    assert "## `profile_library/signify/LCT010/model.json`" in report
    assert "- Path: `$.device_type`" in report


def test_both_file_kinds_are_reported_together(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_json(tmp_path / "profile_library" / "signify" / "manufacturer.json", {})
    write_json(tmp_path / "profile_library" / "signify" / "LCT010" / "model.json", {})

    exit_code, report, _ = run(
        tmp_path,
        monkeypatch,
        ["profile_library/signify/manufacturer.json", "profile_library/signify/LCT010/model.json"],
    )

    assert exit_code == 1
    assert "## `profile_library/signify/manufacturer.json`" in report
    assert "## `profile_library/signify/LCT010/model.json`" in report


@pytest.mark.parametrize(
    "changed_file",
    [
        "profile_library/signify/LCT010/manufacturer.json",
        "profile_library/manufacturer.json",
        "profile_library/signify/LCT010/sub_profile/model.json",
        "docs/source/manufacturer.json",
        "utils/measure/model.json",
    ],
)
def test_files_outside_the_expected_locations_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_file: str,
) -> None:
    write_json(tmp_path / changed_file, {"nope": True})

    exit_code, _, status = run(tmp_path, monkeypatch, [changed_file])

    assert exit_code == 0
    assert status == "success"


def test_deleted_files_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, _, status = run(tmp_path, monkeypatch, ["profile_library/signify/manufacturer.json"])

    assert exit_code == 0
    assert status == "success"


def test_schemas_are_applied_to_their_own_file_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A manufacturer.json must not be judged by the model schema, and vice versa."""
    model_schema = write_json(tmp_path / "model_schema.json", {"type": "object", "required": ["only_in_model"]})
    manufacturer_schema = write_json(
        tmp_path / "manufacturer_schema.json",
        {"type": "object", "required": ["only_in_manufacturer"]},
    )
    write_json(tmp_path / "profile_library" / "signify" / "manufacturer.json", {"only_in_manufacturer": True})
    write_json(tmp_path / "profile_library" / "signify" / "LCT010" / "model.json", {"only_in_model": True})

    exit_code, _, status = run(
        tmp_path,
        monkeypatch,
        ["profile_library/signify/manufacturer.json", "profile_library/signify/LCT010/model.json"],
        model_schema=model_schema,
        manufacturer_schema=manufacturer_schema,
    )

    assert exit_code == 0
    assert status == "success"


def test_library_manufacturer_and_model_files_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard the wiring against the real schemas and a real profile from the library."""
    library = REPOSITORY_ROOT / "profile_library"
    changed_files = ["profile_library/signify/manufacturer.json", "profile_library/signify/LCT010/model.json"]
    for changed_file in changed_files:
        write_json(tmp_path / changed_file, json.loads((REPOSITORY_ROOT / changed_file).read_text(encoding="utf-8")))

    assert library.is_dir()

    exit_code, _, status = run(tmp_path, monkeypatch, changed_files)

    assert exit_code == 0
    assert status == "success"
