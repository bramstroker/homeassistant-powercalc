from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.library.validate_model_json import (
    load_json,
    main,
    sub_profile_schema,
    validate_file,
    validate_files_with_glob,
    validate_manufacturers_with_glob,
    validate_models_with_glob,
)

NAME_SCHEMA = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
MODEL_SCHEMA = Path(__file__).parents[3] / "profile_library" / "model_schema.json"


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def complete_model(device_type: str, **extra: object) -> dict[str, object]:
    """Return the smallest complete profile for exercising the real model schema."""
    return {
        "name": "Example device",
        "device_type": device_type,
        "measure_method": "manual",
        "measure_device": "Shelly PM Mini Gen3",
        "calculation_strategy": "fixed",
        "fixed_config": {"power": 5},
        "created_at": "2026-08-30T00:00:00Z",
        **extra,
    }


def test_load_json(tmp_path: Path) -> None:
    path = write_json(tmp_path / "model.json", {"name": "LCT010"})

    assert load_json(str(path)) == {"name": "LCT010"}


def test_valid_file_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_json(tmp_path / "model.json", {"name": "LCT010"})

    validate_file(str(path), NAME_SCHEMA)

    assert capsys.readouterr().out == f"VALID: {path}\n"


def test_file_violating_the_schema_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_json(tmp_path / "model.json", {"name": 42})

    validate_file(str(path), NAME_SCHEMA)

    assert capsys.readouterr().out == f"INVALID: {path}\nError: 42 is not of type 'string'\n"


def test_unreadable_file_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "model.json"
    path.write_text("{not json", encoding="utf-8")

    validate_file(str(path), NAME_SCHEMA)

    assert capsys.readouterr().out.startswith(f"ERROR: {path}\nError: ")


def test_generic_device_specs_allow_rated_power_and_connectivity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(
        tmp_path / "model.json",
        complete_model(
            "smart_speaker",
            device_specs={"rated_power": 15, "connectivity": ["wifi", "ethernet", "usb"]},
        ),
    )

    assert validate_file(str(path), load_json(str(MODEL_SCHEMA))) is True
    assert capsys.readouterr().out == f"VALID: {path}\n"


def test_connectivity_is_not_allowed_at_the_model_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(tmp_path / "model.json", complete_model("smart_speaker", connectivity=["wifi"]))

    assert validate_file(str(path), load_json(str(MODEL_SCHEMA))) is False
    assert "Additional properties are not allowed ('connectivity' was unexpected)" in capsys.readouterr().out


def test_light_specs_extend_generic_device_specs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_json(
        tmp_path / "model.json",
        complete_model(
            "light",
            standby_power=0.2,
            device_specs={
                "socket": "E27",
                "form_factor": "bulb",
                "lumens": 806,
                "rated_power": 9.5,
                "connectivity": ["zigbee"],
            },
        ),
    )

    assert validate_file(str(path), load_json(str(MODEL_SCHEMA))) is True
    assert capsys.readouterr().out == f"VALID: {path}\n"


@pytest.mark.parametrize(
    "device_type,device_specs",
    [
        ("smart_switch", {"form_factor": "plug", "max_load_watts": 3680}),
        ("smart_dimmer", {"form_factor": "in_wall", "max_load_watts": 200}),
        ("network", {"form_factor": "router"}),
        ("fan", {"form_factor": "air_purifier"}),
        ("smart_speaker", {"form_factor": "soundbar"}),
    ],
)
def test_type_specific_device_specs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    device_type: str,
    device_specs: dict[str, object],
) -> None:
    path = write_json(
        tmp_path / device_type / "model.json",
        complete_model(device_type, device_specs={**device_specs, "connectivity": ["wifi"]}),
    )

    assert validate_file(str(path), load_json(str(MODEL_SCHEMA))) is True
    assert capsys.readouterr().out == f"VALID: {path}\n"


def test_type_specific_device_specs_are_rejected_for_other_device_types(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(
        tmp_path / "model.json",
        complete_model("network", device_specs={"form_factor": "router", "max_load_watts": 100}),
    )

    assert validate_file(str(path), load_json(str(MODEL_SCHEMA))) is False
    assert "Unevaluated properties are not allowed ('max_load_watts' was unexpected)" in capsys.readouterr().out


def test_validate_files_with_glob_walks_matches_in_order(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    schema = write_json(tmp_path / "schema.json", NAME_SCHEMA)
    write_json(tmp_path / "signify" / "manufacturer.json", {"name": "signify"})
    write_json(tmp_path / "govee" / "manufacturer.json", {"name": "govee"})
    write_json(tmp_path / "govee" / "H61F5" / "model.json", {"name": "H61F5"})

    validate_files_with_glob(str(tmp_path), "*/manufacturer.json", str(schema))

    assert capsys.readouterr().out == (
        f"VALID: {tmp_path / 'govee' / 'manufacturer.json'}\nVALID: {tmp_path / 'signify' / 'manufacturer.json'}\n"
    )


def test_validate_models_with_glob_covers_profiles_and_their_sub_profiles(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema = write_json(tmp_path / "schema.json", NAME_SCHEMA)
    write_json(tmp_path / "signify" / "LCT010" / "model.json", {"name": "LCT010"})
    write_json(tmp_path / "signify" / "manufacturer.json", {"name": "signify"})
    write_json(tmp_path / "signify" / "LCT010" / "length_2m" / "model.json", {"name": "2 metre"})

    assert validate_models_with_glob(str(tmp_path), str(schema)) is True

    assert capsys.readouterr().out == (
        f"VALID: {tmp_path / 'signify' / 'LCT010' / 'model.json'}\n"
        f"VALID: {tmp_path / 'signify' / 'LCT010' / 'length_2m' / 'model.json'}\n"
    )


def test_validate_models_with_glob_reports_an_invalid_sub_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema = write_json(tmp_path / "schema.json", {**NAME_SCHEMA, "additionalProperties": False})
    write_json(tmp_path / "signify" / "LCT010" / "model.json", {"name": "LCT010"})
    write_json(tmp_path / "signify" / "LCT010" / "length_2m" / "model.json", {"nope": True})

    assert validate_models_with_glob(str(tmp_path), str(schema)) is False

    assert "INVALID" in capsys.readouterr().out


def test_sub_profile_schema_drops_the_rules_that_only_hold_for_a_whole_profile() -> None:
    schema = {
        "type": "object",
        "required": ["name", "device_type"],
        "allOf": [{"if": {"const": "light"}, "then": {"required": ["standby_power"]}}],
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}, "standby_power": {"type": "number", "minimum": 0.05}},
    }

    derived = sub_profile_schema(schema)

    assert "required" not in derived
    assert "allOf" not in derived
    assert derived["additionalProperties"] is False
    assert derived["properties"]["standby_power"]["minimum"] == 0
    assert schema["properties"]["standby_power"]["minimum"] == 0.05


def test_sub_profile_may_zero_a_power_value_a_complete_profile_may_not(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A sub profile setting 0 is overriding its parent, not skipping a measurement."""
    schema = write_json(
        tmp_path / "schema.json",
        {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}, "standby_power": {"type": "number", "minimum": 0.05}},
        },
    )
    write_json(tmp_path / "signify" / "LCT010" / "model.json", {"name": "LCT010", "standby_power": 0.4})
    write_json(tmp_path / "signify" / "LCT010" / "nightlight" / "model.json", {"standby_power": 0})

    assert validate_models_with_glob(str(tmp_path), str(schema)) is True
    assert "INVALID" not in capsys.readouterr().out


def test_validate_manufacturers_with_glob_only_matches_manufacturer_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema = write_json(tmp_path / "schema.json", NAME_SCHEMA)
    write_json(tmp_path / "signify" / "manufacturer.json", {"name": "signify"})
    write_json(tmp_path / "signify" / "LCT010" / "model.json", {"nope": True})
    write_json(tmp_path / "manufacturer.json", {"nope": True})

    validate_manufacturers_with_glob(str(tmp_path), str(schema))

    assert capsys.readouterr().out == f"VALID: {tmp_path / 'signify' / 'manufacturer.json'}\n"


def test_main_validates_manufacturers_and_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library = tmp_path / "profile_library"
    write_json(library / "signify" / "manufacturer.json", {"name": "Signify", "aliases": ["Philips"]})
    write_json(
        library / "signify" / "LCT010" / "model.json",
        {
            "name": "Hue White and Color Ambiance",
            "device_type": "light",
            "calculation_strategy": "lut",
            "measure_method": "script",
            "measure_device": "Shelly PM Mini Gen3",
            "created_at": "2024-12-20T00:55:44Z",
            "standby_power": 0.4,
        },
    )
    monkeypatch.setattr("utils.library.validate_model_json.PROFILE_DIRECTORY", str(library))

    main()

    assert capsys.readouterr().out == (
        f"VALID: {library / 'signify' / 'manufacturer.json'}\nVALID: {library / 'signify' / 'LCT010' / 'model.json'}\n"
    )
