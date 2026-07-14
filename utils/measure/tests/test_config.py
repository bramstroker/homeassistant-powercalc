from __future__ import annotations

from measure.cli.environment import CliEnvironment
from measure.const import MeasureType
from measure.powermeter.const import PowerMeterType
import pytest


def test_cli_environment_preserves_manual_power_meter_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_METER", PowerMeterType.MANUAL)
    monkeypatch.setenv("SAMPLE_COUNT", "9")
    monkeypatch.setenv("CT_BRI_STEPS", "2")
    monkeypatch.setenv("CT_MIRED_STEPS", "3")

    config = CliEnvironment()

    assert config.selected_power_meter == PowerMeterType.MANUAL
    assert config.sample_count == 1
    assert config.ct_bri_steps == 15
    assert config.ct_mired_steps == 50
    assert config.bri_bri_steps == 3


def test_cli_environment_preserves_value_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_METER", PowerMeterType.HASS)
    monkeypatch.setenv("MIN_BRIGHTNESS", "0")
    monkeypatch.setenv("MAX_SAT", "999")
    monkeypatch.setenv("HS_BRI_PRECISION", "2")
    monkeypatch.setenv("MEASURE_TIME_EFFECT", "12")
    monkeypatch.setenv("MEASURE_TIME_EFFECT_MIN", "30")
    monkeypatch.setenv("MEASURE_TIME_EFFECT_CONVERGENCE_WINDOW", "20")
    monkeypatch.setenv("MEASURE_TIME_EFFECT_CONVERGENCE_REL", "2.5")
    monkeypatch.setenv("SELECTED_MEASURE_TYPE", "Average")

    config = CliEnvironment()

    assert config.min_brightness == 1
    assert config.max_sat == 255
    assert config.hs_bri_precision == 2
    assert config.hs_bri_steps == 16
    assert config.measure_time_effect_min == 12
    assert config.measure_time_effect_convergence_window == 12
    assert config.measure_time_effect_convergence_rel == pytest.approx(0.025)
    assert config.selected_measure_type == MeasureType.AVERAGE
