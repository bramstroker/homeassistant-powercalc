from __future__ import annotations

import asyncio
import csv
import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from utils.library import update_library
from utils.library.update_library import (
    generate_library_json,
    get_color_modes,
    process_author_update,
    process_model_file,
)


def test_get_color_modes_only_includes_known_lut_color_modes(tmp_path: Path) -> None:
    for filename in ("brightness.csv.gz", "color_temp.csv", "effect.csv.gz", "tapering.csv.gz"):
        (tmp_path / filename).touch()

    assert asyncio.run(get_color_modes(str(tmp_path))) == {"brightness", "color_temp", "effect"}


def test_process_model_file_adds_lut_quality(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path)
    write_brightness_lut(model_directory / "brightness.csv.gz", rough=True)

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert model["lut_quality"]["score"] == model["lut_quality"]["brightness"]
    assert 0 < model["lut_quality"]["score"] < 100


def test_process_model_file_survives_an_unreadable_lut(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path)
    (model_directory / "brightness.csv.gz").write_bytes(b"not gzip")

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert "lut_quality" not in model


def test_process_model_file_omits_lut_quality_without_lut_files(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path, calculation_strategy="fixed")

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert "lut_quality" not in model


def test_process_model_file_calculates_power_values_from_sub_profiles(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path, calculation_strategy="fixed")
    (model_directory / "model.json").write_text(
        json.dumps(
            {
                "name": "Hue White and Color Ambiance",
                "calculation_strategy": "fixed",
                "fixed_config": {"power": 1},
                "standby_power": 0.2,
            },
        ),
    )
    low_profile = model_directory / "low"
    low_profile.mkdir()
    (low_profile / "model.json").write_text(
        json.dumps({"fixed_config": {"power": 4}, "standby_power": 0.3}),
    )
    high_profile = model_directory / "high"
    high_profile.mkdir()
    (high_profile / "model.json").write_text(
        json.dumps({"fixed_config": {"power": 8}, "standby_power": 0.5}),
    )

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert model["max_power"] == 8
    assert model["standby_power"] == 0.5
    assert model["sub_profile_count"] == 2


def test_process_model_file_uses_inherited_sub_profile_power_values(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path, calculation_strategy="fixed")
    (model_directory / "model.json").write_text(
        json.dumps(
            {
                "name": "Hue White and Color Ambiance",
                "calculation_strategy": "fixed",
                "fixed_config": {"power": 6},
                "standby_power": 0.4,
            },
        ),
    )
    sub_profile = model_directory / "inherited"
    sub_profile.mkdir()
    (sub_profile / "model.json").write_text(json.dumps({"name": "Inherited"}))

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert model["max_power"] == 6
    assert model["standby_power"] == 0.4


def test_library_json_hash_ignores_lut_quality(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hash drives profile re-downloads, so a score change must not invalidate every install."""
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    (tmp_path / "signify").mkdir()
    (tmp_path / "signify" / "manufacturer.json").write_text(json.dumps({"name": "Signify", "aliases": []}))

    first = generate_library(tmp_path, {"score": 96.4, "brightness": 96.4})
    second = generate_library(tmp_path, {"score": 42.0, "brightness": 42.0})

    assert first["lut_quality"] == {"score": 96.4, "brightness": 96.4}
    assert second["lut_quality"] == {"score": 42.0, "brightness": 42.0}
    assert first["hash"] == second["hash"]


def test_generate_library_json_sorts_manufacturers_and_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    for manufacturer in ("zeta", "alpha"):
        manufacturer_directory = tmp_path / manufacturer
        manufacturer_directory.mkdir()
        (manufacturer_directory / "manufacturer.json").write_text(json.dumps({"name": manufacturer.title()}))

    models = [
        {"id": "Z Model", "manufacturer": "alpha", "device_type": "light"},
        {"id": "A Model", "manufacturer": "zeta", "device_type": "light"},
        {"id": "A Model", "manufacturer": "alpha", "device_type": "light"},
    ]

    asyncio.run(generate_library_json(models))

    library = json.loads((tmp_path / "library.json").read_text())
    assert [manufacturer["name"] for manufacturer in library["manufacturers"]] == ["alpha", "zeta"]
    assert [model["id"] for model in library["manufacturers"][0]["models"]] == ["A Model", "Z Model"]


def test_process_author_update_migrates_legacy_author_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    model_path = tmp_path / "signify" / "LCT012" / "model.json"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(json.dumps({"author_info": {"name": "Test User", "github": "test-user"}}))

    asyncio.run(process_author_update(str(model_path)))

    assert json.loads(model_path.read_text()) == {"authors": [{"name": "Test User", "github": "test-user"}]}


def test_process_model_file_adds_the_power_range_of_the_lut(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path)
    write_brightness_lut(model_directory / "brightness.csv.gz", rough=False)

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert model["power_range"] == {"min": 1.0, "max": 20.0}
    assert model["max_power"] == 20.0


def test_process_model_file_spans_the_power_range_over_sub_profiles(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path, calculation_strategy="fixed")
    (model_directory / "model.json").write_text(
        json.dumps({"name": "Hue Play", "calculation_strategy": "fixed", "fixed_config": {"power": 5}}),
    )
    for name, power in (("low", 2), ("high", 9)):
        sub_profile = model_directory / name
        sub_profile.mkdir()
        (sub_profile / "model.json").write_text(json.dumps({"fixed_config": {"power": power}}))

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert model["power_range"] == {"min": 2, "max": 9}


def test_process_model_file_takes_the_power_range_from_linear_calibration(tmp_path: Path) -> None:
    model_directory = create_model_directory(tmp_path, calculation_strategy="linear")
    (model_directory / "model.json").write_text(
        json.dumps(
            {
                "name": "Dimmer",
                "calculation_strategy": "linear",
                "linear_config": {"calibrate": ["1 -> 1.214", "128 -> 1.484", "255 -> 1.659"]},
            },
        ),
    )

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert model["power_range"] == {"min": 1.214, "max": 1.659}


def test_process_model_file_omits_the_power_range_when_the_low_end_is_unknown(tmp_path: Path) -> None:
    """A linear profile without calibration points only knows its maximum."""
    model_directory = create_model_directory(tmp_path, calculation_strategy="linear")
    (model_directory / "model.json").write_text(
        json.dumps({"name": "Dimmer", "calculation_strategy": "linear", "linear_config": {"max_power": 0.4}}),
    )

    model = asyncio.run(process_model_file(str(model_directory / "model.json")))

    assert "power_range" not in model
    assert model["max_power"] == 0.4


def test_library_json_hash_ignores_the_generated_measurement_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regenerating these must not send every install off to re-download every profile."""
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    (tmp_path / "signify").mkdir()
    (tmp_path / "signify" / "manufacturer.json").write_text(json.dumps({"name": "Signify", "aliases": []}))

    model: dict[str, Any] = {
        "id": "LCT012",
        "manufacturer": "signify",
        "name": "Hue White and Color Ambiance",
        "device_type": "light",
        "power_range": {"min": 0.72, "max": 8.5},
        "measurement_updated_at": "2024-05-03T09:11:32",
    }
    asyncio.run(generate_library_json([model]))
    first = json.loads((tmp_path / "library.json").read_text())["manufacturers"][0]["models"][0]

    asyncio.run(
        generate_library_json(
            [{**model, "power_range": {"min": 0.8, "max": 9.0}, "measurement_updated_at": "2026-08-29T07:23:00"}],
        ),
    )
    second = json.loads((tmp_path / "library.json").read_text())["manufacturers"][0]["models"][0]

    assert first["power_range"] != second["power_range"]
    assert first["hash"] == second["hash"]


def test_generate_library_json_carries_manufacturer_brand_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    (tmp_path / "signify").mkdir()
    (tmp_path / "signify" / "manufacturer.json").write_text(
        json.dumps(
            {
                "name": "Signify",
                "aliases": ["Philips"],
                "website": "https://www.signify.com",
                "country": "NL",
                "description": "Dutch lighting manufacturer, formerly Philips Lighting.",
            },
        ),
    )

    asyncio.run(generate_library_json([{"id": "LCT012", "manufacturer": "signify", "device_type": "light"}]))

    manufacturer = json.loads((tmp_path / "library.json").read_text())["manufacturers"][0]
    assert manufacturer["website"] == "https://www.signify.com"
    assert manufacturer["country"] == "NL"
    assert manufacturer["description"].startswith("Dutch lighting")


def test_generate_library_json_leaves_out_brand_details_a_manufacturer_does_not_have(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    (tmp_path / "govee").mkdir()
    (tmp_path / "govee" / "manufacturer.json").write_text(json.dumps({"name": "Govee"}))

    asyncio.run(generate_library_json([{"id": "H61F5", "manufacturer": "govee", "device_type": "light"}]))

    manufacturer = json.loads((tmp_path / "library.json").read_text())["manufacturers"][0]
    assert "website" not in manufacturer
    assert "country" not in manufacturer


def generate_library(data_dir: Path, lut_quality: dict[str, float]) -> dict[str, Any]:
    """Run the library.json generation for a single model and return its entry."""
    model = {
        "id": "LCT012",
        "manufacturer": "signify",
        "name": "Hue White and Color Ambiance",
        "device_type": "light",
        "lut_quality": lut_quality,
    }
    asyncio.run(generate_library_json([model]))

    library = json.loads((data_dir / "library.json").read_text())
    return library["manufacturers"][0]["models"][0]


def create_model_directory(tmp_path: Path, *, calculation_strategy: str = "lut") -> Path:
    model_directory = tmp_path / "signify" / "LCT012"
    model_directory.mkdir(parents=True)
    (model_directory / "model.json").write_text(
        json.dumps({"name": "Hue White and Color Ambiance", "calculation_strategy": calculation_strategy}),
    )
    return model_directory


def write_brightness_lut(path: Path, *, rough: bool) -> None:
    rows = [(bri, float(bri)) for bri in range(1, 21)]
    if rough:
        rows[10] = (11, 25.0)

    with gzip.open(path, "wt", newline="") as lut_file:
        writer = csv.writer(lut_file)
        writer.writerow(["bri", "watt"])
        writer.writerows(rows)
