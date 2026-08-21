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


def test_process_author_update_migrates_legacy_author_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update_library, "DATA_DIR", str(tmp_path))
    model_path = tmp_path / "signify" / "LCT012" / "model.json"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(json.dumps({"author_info": {"name": "Test User", "github": "test-user"}}))

    asyncio.run(process_author_update(str(model_path)))

    assert json.loads(model_path.read_text()) == {"authors": [{"name": "Test User", "github": "test-user"}]}


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
