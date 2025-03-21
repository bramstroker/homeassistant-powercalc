import os.path
from unittest.mock import MagicMock

import pytest
from measure.controller.light.const import LutMode
from measure.runner.const import QUESTION_MODE
from measure.runner.light import LightRunner
from measure.util.measure_util import MeasureUtil


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


def test_run(mock_config_factory, export_path: str) -> None:  # noqa: ANN001
    mock_config = mock_config_factory()

    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, mock_config)
    runner.prepare({QUESTION_MODE: {LutMode.BRIGHTNESS}})

    runner.run({}, export_path)

    assert os.path.exists(os.path.join(export_path, "brightness.csv.gz"))
