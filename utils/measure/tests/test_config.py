import logging
from pathlib import Path

from decouple import Config, RepositoryEnv
import measure.cli.environment as environment
from measure.cli.environment import CliEnvironment
from measure.const import PARAMETER_LIMITS, MeasureType
from measure.powermeter.const import PowerMeterType
import pytest

# Fields without their own env var: bri_bri_steps is fixed, the hs_*_steps are
# derived from the HS_*_PRECISION vars and cannot leave their table range.
_DERIVED_LIMIT_FIELDS = {"bri_bri_steps", "hs_bri_steps", "hs_hue_steps", "hs_sat_steps"}
_ENV_BACKED_LIMIT_FIELDS = sorted(set(PARAMETER_LIMITS) - _DERIVED_LIMIT_FIELDS)


def test_missing_measurement_selection_leaves_the_cli_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELECTED_MEASURE_TYPE", raising=False)
    monkeypatch.setattr(environment, "config", Config({}))

    assert CliEnvironment().selected_measure_type is None


def test_environment_overrides_dotenv_answers_without_normalizing_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("MODEL_ID=From file\nSELECTED_MEASURE_TYPE=Average\n", encoding="utf-8")
    monkeypatch.setattr(environment, "config", Config(RepositoryEnv(str(dotenv))))
    monkeypatch.delenv("MODEL_ID", raising=False)
    monkeypatch.delenv("SELECTED_MEASURE_TYPE", raising=False)
    config = CliEnvironment()

    assert config.get_conf_value("MODEL_ID") == "From file"
    assert config.selected_measure_type == MeasureType.AVERAGE

    monkeypatch.setenv("MODEL_ID", " Model with spaces ")
    monkeypatch.setenv("SELECTED_MEASURE_TYPE", "recorder")

    assert config.get_conf_value("MODEL_ID") == " Model with spaces "
    assert config.selected_measure_type == MeasureType.RECORDER


def test_optional_environment_answer_distinguishes_missing_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment, "config", Config({}))
    monkeypatch.delenv("MODEL_ID", raising=False)
    config = CliEnvironment()

    assert config.get_conf_value("MODEL_ID") is None

    monkeypatch.setenv("MODEL_ID", "")

    assert config.get_conf_value("MODEL_ID") == ""


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


def test_cli_environment_preserves_named_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    assert CliEnvironment().log_level == "DEBUG"


@pytest.mark.parametrize("name", _ENV_BACKED_LIMIT_FIELDS)
def test_cli_environment_clamps_env_values_to_parameter_limits(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minimum, maximum = PARAMETER_LIMITS[name]
    if name == "measure_time_effect_min":
        # Otherwise the relative cap min(value, measure_time_effect) hides the table clamp.
        monkeypatch.setenv("MEASURE_TIME_EFFECT", str(int(PARAMETER_LIMITS["measure_time_effect"][1])))
    config = CliEnvironment()

    monkeypatch.setenv(name.upper(), str(int(maximum) + 1))
    assert getattr(config, name) == maximum

    monkeypatch.setenv(name.upper(), str(int(minimum) - 1))
    assert getattr(config, name) == minimum


def test_cli_environment_warns_when_clamping(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SAMPLE_COUNT", "500")

    with caplog.at_level(logging.WARNING, logger="measure"):
        assert CliEnvironment().sample_count == 100

    assert "SAMPLE_COUNT=500 is outside the allowed range [1, 100]; using 100" in caplog.text
