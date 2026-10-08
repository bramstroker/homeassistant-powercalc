import json
from pathlib import Path

from measure.profile.model_json import write_model_json
from measure.tuning import MeasurementParameters
import pytest


def test_model_export_omits_unmeasured_optional_values(tmp_path: Path) -> None:
    path = write_model_json(
        tmp_path,
        standby_power=None,
        name="Test device",
        measure_device="Test meter",
        parameters=MeasurementParameters(sample_count=3),
    )

    assert path == tmp_path / "model.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "Test device"
    assert data["measure_device"] == "Test meter"
    assert data["measure_settings"]["SAMPLE_COUNT"] == 3
    assert data["measure_settings"]["DUMMY_LOAD"] is False
    assert "standby_power" not in data
    assert "voltage_range" not in data
    assert "mains_voltage" not in data
    assert "NUM_LIGHTS" not in data["measure_settings"]
    assert "DUMMY_LOAD_RESISTANCE" not in data["measure_settings"]
    assert "DUMMY_LOAD_POWER" not in data["measure_settings"]


@pytest.mark.parametrize("voltages", [None, [], [229.0, 231.0]])
def test_dummy_load_power_export_requires_voltage_readings(tmp_path: Path, voltages: list[float] | None) -> None:
    path = write_model_json(
        tmp_path,
        standby_power=0.0,
        name="Test device",
        measure_device="Test meter",
        parameters=MeasurementParameters(),
        dummy_load=True,
        dummy_load_resistance=4700.123,
        voltages=voltages,
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["standby_power"] == 0.0
    settings = data["measure_settings"]
    assert settings["DUMMY_LOAD"] is True
    assert settings["DUMMY_LOAD_RESISTANCE"] == 4700.12
    if voltages:
        assert settings["DUMMY_LOAD_POWER"] == 11.26
        assert data["voltage_range"] == {"min": 229.0, "max": 231.0}
        assert data["mains_voltage"] == 230
    else:
        assert "DUMMY_LOAD_POWER" not in settings
        assert "voltage_range" not in data
        assert "mains_voltage" not in data
