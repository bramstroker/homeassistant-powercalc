import csv
import os.path
from unittest.mock import MagicMock, patch

from measure.controller.light.const import LutMode
from measure.runner.const import QUESTION_MODE
from measure.runner.light import EffectVariation, LightRunner
from measure.util.measure_util import MeasureUtil
import pytest


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
def test_get_variations(mock_config_factory, mode: LutMode, expected_count: int) -> None:  # noqa: ANN001
    mock_config = mock_config_factory()

    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, mock_config)
    runner.prepare({QUESTION_MODE: mode})

    variations = runner.get_variations(mode)
    assert len(list(variations)) == expected_count


@patch("time.sleep", return_value=None)
def test_run(mock_sleep, mock_config_factory, export_path: str) -> None:  # noqa: ANN001
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


def test_resume_effect(mock_config_factory, tmp_path: str) -> None:  # noqa: ANN001
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
