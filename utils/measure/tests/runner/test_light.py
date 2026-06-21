import csv
import os.path
from pathlib import Path
from unittest.mock import MagicMock

from measure.controller.light.const import LutMode
from measure.runner.const import QUESTION_MODE
from measure.runner.light import EffectVariation, LightRunner
from measure.util.measure_util import AverageMeasurementConvergence, MeasurementResult, MeasureUtil
import pytest

from tests.conftest import MockConfigFactory


@pytest.mark.parametrize(
    "mode,expected_count",
    [
        (
            LutMode.BRIGHTNESS,
            255,
        ),
        (
            LutMode.COLOR_TEMP,
            1872,
        ),
        (
            LutMode.HS,
            2025,
        ),
        (
            LutMode.EFFECT,
            24,
        ),
    ],
)
def test_get_variations(mock_config_factory: MockConfigFactory, mode: LutMode, expected_count: int) -> None:
    mock_config = mock_config_factory()

    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, mock_config)
    runner.prepare({QUESTION_MODE: mode})

    variations = runner.get_variations(mode)
    assert len(list(variations)) == expected_count


def test_run(mock_config_factory: MockConfigFactory, export_path: str) -> None:
    mock_config = mock_config_factory()

    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, mock_config)
    runner.prepare({QUESTION_MODE: {LutMode.BRIGHTNESS}})

    result = runner.run({}, export_path)
    assert result.model_json_data == {
        "device_type": "light",
        "calculation_strategy": "lut",
    }

    assert os.path.exists(os.path.join(export_path, "brightness.csv.gz"))


def test_resume_effect(mock_config_factory: MockConfigFactory, tmp_path: Path) -> None:
    """Test resume point is detected correctly for effect mode."""
    csv_file = tmp_path / "effect.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["effect", "bri", "watt"])
        writer.writerow(["colorloop", 100, 2.5])
        writer.writerow(["nightlight", 200, 3.0])

    mock_config = mock_config_factory()
    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, mock_config)

    resume_variation = runner.get_resume_variation(str(csv_file), LutMode.EFFECT)
    assert isinstance(resume_variation, EffectVariation)
    assert resume_variation.effect == "nightlight"
    assert resume_variation.bri == 200


def test_effect_measurement_uses_convergence_settings(mock_config_factory: MockConfigFactory) -> None:
    mock_config = mock_config_factory(
        config_values={
            "measure_time_effect": 180,
            "measure_time_effect_min": 20,
            "measure_time_effect_convergence_window": 15,
            "measure_time_effect_convergence_abs": 0.1,
            "measure_time_effect_convergence_rel": 0.01,
        },
    )
    measure_util_mock = MagicMock(MeasureUtil)
    measure_util_mock.take_average_measurement.return_value = MeasurementResult(power=10, voltages=[])
    runner = LightRunner(measure_util_mock, mock_config)

    runner.take_power_measurement(LutMode.EFFECT, start_timestamp=0)

    measure_util_mock.take_average_measurement.assert_called_once_with(
        180,
        convergence=AverageMeasurementConvergence(
            min_duration=20,
            window_duration=15,
            absolute_threshold=0.1,
            relative_threshold=0.01,
        ),
    )


def test_get_questions(mock_config_factory: MockConfigFactory) -> None:
    """Test get_questions contains the new triple mode choice when effects are supported."""
    mock_config = mock_config_factory()
    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, mock_config)

    questions = runner.get_questions()
    mode_question = next(q for q in questions if q.name == QUESTION_MODE)
    choices = mode_question.choices

    assert ("hs + color_temp + effect", {LutMode.HS, LutMode.COLOR_TEMP, LutMode.EFFECT}) in choices
