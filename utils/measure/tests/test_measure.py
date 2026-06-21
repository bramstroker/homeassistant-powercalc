from collections.abc import Iterator
import csv
from io import StringIO
import json
import logging
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import inquirer
from inquirer import events
from inquirer.render import ConsoleRender
from measure.config import MeasureConfig
from measure.const import (
    MODEL_JSON_MAX_VOLTAGE,
    MODEL_JSON_MIN_VOLTAGE,
    PROJECT_DIR,
    QUESTION_MODEL_ID,
    QUESTION_SELECTED_MEASURE_TYPE,
    MeasureType,
)
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.light.const import LutMode
from measure.measure import Measure
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.runner.const import (
    QUESTION_CHARGING_DEVICE_TYPE,
    QUESTION_COLOR_MODE,
    QUESTION_DURATION,
    QUESTION_EXPORT_FILENAME,
    QUESTION_GZIP,
    QUESTION_MODE,
)
from measure.runner.speaker import QUESTION_DISABLE_STREAMING
from measure.util.measure_util import (
    AverageMeasurementConvergence,
    AverageMeasurementSnapshot,
    MeasurementResult,
    MeasureUtil,
)
import pytest
from readchar import key

from tests.conftest import MockConfigFactory


@pytest.fixture(autouse=True)
def _mock_input() -> Iterator[None]:
    with patch("builtins.input", return_value=""):
        yield


@pytest.fixture
def mock_average_measurement() -> Iterator[MagicMock]:
    with patch.object(
        MeasureUtil,
        "take_average_measurement",
        return_value=MeasurementResult(power=1.5, voltages=[]),
    ) as mock_take_measurement:
        yield mock_take_measurement


class EventGenerator:
    def __init__(self, *args: str) -> None:
        self.iterator: Iterator[str] = args.__iter__()

    def next(self) -> events.KeyPressed:
        return events.KeyPressed(next(self.iterator))


def event_factory(*args: str) -> EventGenerator:
    return EventGenerator(*args)


def test_wizard(mock_config_factory: MockConfigFactory) -> None:
    """Test the CLI wizard, can we actually select certain options"""
    mock_config = mock_config_factory(
        set_question_defaults=False,
    )
    measure = _create_measure_instance(
        mock_config,
        console_events=event_factory(
            # MEASURE_TYPE
            key.ENTER,
            # GENERATE_MODEL_JSON
            "y",
            # DUMMY_LOAD
            "n",
            # MODEL_ID
            "m",
            key.ENTER,
            # MODEL_NAME
            "a",
            key.ENTER,
            # MEASURE_DEVICE
            "a",
            key.ENTER,
            # COLOR_MODE
            key.DOWN,
            key.DOWN,
            key.ENTER,
            # GZIP
            key.ENTER,
            # MULTIPLE_LIGHTS
            "n",
        ),
    )

    measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/m/brightness.csv.gz"))
    assert os.path.exists(os.path.join(PROJECT_DIR, "export/m/model.json"))


def test_run_light(mock_config_factory: MockConfigFactory) -> None:
    """Simulate a full run of the light measure using brightness mode"""
    mock_config = mock_config_factory()

    measure = _create_measure_instance(config=mock_config)
    measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/LCT010/brightness.csv.gz"))
    model_json_path = os.path.join(PROJECT_DIR, "export/LCT010/model.json")
    assert os.path.exists(model_json_path)
    with open(model_json_path) as model_json_file:
        model_json = json.load(model_json_file)
    assert model_json[MODEL_JSON_MIN_VOLTAGE] == 233.0
    assert model_json[MODEL_JSON_MAX_VOLTAGE] == 233.0


def test_take_measurement_tracks_voltage_range(mock_config_factory: MockConfigFactory) -> None:
    mock_config = mock_config_factory(config_values={"sample_count": 3})
    power_meter = SequencePowerMeter(
        [
            PowerMeasurementResult(power=1.0, updated=1.0, voltage=231.2),
            PowerMeasurementResult(power=2.0, updated=2.0, voltage=229.9),
            PowerMeasurementResult(power=3.0, updated=3.0, voltage=230.4),
        ],
    )
    measure_util = MeasureUtil(
        power_meter,
        mock_config,
        include_voltage=lambda: True,
    )

    result = measure_util.take_measurement()
    assert result.power == 2.0
    assert result.voltages == [231.2, 229.9, 230.4]


@pytest.mark.parametrize(
    ("absolute_threshold", "relative_threshold", "snapshots", "expected"),
    [
        pytest.param(0.1, 0.01, [(0, 10.0), (19, 10.0)], False, id="before-min"),
        pytest.param(0.1, 0.01, [(5, 10.0), (20, 10.09)], True, id="abs-stable"),
        pytest.param(0.01, 0.01, [(5, 100.0), (20, 100.5)], True, id="rel-stable"),
        pytest.param(0.1, 0.01, [(5, 10.0), (20, 11.0)], False, id="unstable"),
    ],
)
def test_average_convergence(
    absolute_threshold: float,
    relative_threshold: float,
    snapshots: list[tuple[float, float]],
    expected: bool,
) -> None:
    convergence = AverageMeasurementConvergence(
        min_duration=20,
        window_duration=15,
        absolute_threshold=absolute_threshold,
        relative_threshold=relative_threshold,
    )
    average_snapshots = [AverageMeasurementSnapshot(elapsed=elapsed, average=average) for elapsed, average in snapshots]

    assert MeasureUtil.average_has_converged(average_snapshots, convergence) is expected


def test_run_smart_speaker(mock_config_factory: MockConfigFactory, mock_average_measurement: MagicMock) -> None:
    """Simulate a full run of the speaker measure"""
    mock_config = mock_config_factory(
        question_defaults={
            QUESTION_SELECTED_MEASURE_TYPE: MeasureType.SPEAKER,
            QUESTION_DISABLE_STREAMING: False,
        },
    )

    with (
        patch("measure.runner.speaker.SLEEP_PRE_MEASURE", 0),
        patch("measure.runner.speaker.SLEEP_MUTE", 0),
    ):
        measure = _create_measure_instance(config=mock_config)
        measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/LCT010/model.json"))


def test_run_charging(mock_config_factory: MockConfigFactory, mock_average_measurement: MagicMock) -> None:
    """Simulate a full run of the charging measure"""
    mock_config = mock_config_factory(
        question_defaults={
            QUESTION_SELECTED_MEASURE_TYPE: MeasureType.CHARGING,
            QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
        },
    )

    measure = _create_measure_instance(config=mock_config)
    measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/LCT010/model.json"))


def test_run_fan(mock_config_factory: MockConfigFactory, mock_average_measurement: MagicMock) -> None:
    """Simulate a full run of the fan measure"""
    mock_config = mock_config_factory(
        question_defaults={
            QUESTION_SELECTED_MEASURE_TYPE: MeasureType.FAN,
        },
    )

    measure = _create_measure_instance(config=mock_config)
    measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/LCT010/model.json"))


def test_run_recorder(mock_config_factory: MockConfigFactory) -> None:
    """Simulate a full run of the recorder measure"""
    mock_config = mock_config_factory(
        question_defaults={
            QUESTION_SELECTED_MEASURE_TYPE: MeasureType.RECORDER,
            QUESTION_EXPORT_FILENAME: "test.csv",
        },
    )

    def side_effect(_: Any) -> MeasurementResult:  # noqa: ANN401
        if side_effect.counter >= 5:
            raise KeyboardInterrupt
        side_effect.counter += 1
        return MeasurementResult(power=1.5, voltages=[])

    side_effect.counter = 0

    # Mock take_measurement to call the side_effect function after 5 iterations
    with patch.object(MeasureUtil, "take_measurement", side_effect=side_effect):
        measure = _create_measure_instance(config=mock_config)
        measure.start()

    csv_filepath = os.path.join(PROJECT_DIR, "export/generic/test.csv")
    assert os.path.exists(csv_filepath)

    with open(csv_filepath, newline="") as csv_file:
        reader = csv.reader(csv_file)
        lines = list(reader)

    assert len(lines) == 5


def test_run_average(
    mock_config_factory: MockConfigFactory,
    caplog: pytest.LogCaptureFixture,
    mock_average_measurement: MagicMock,
) -> None:
    """Simulate a full run of the average measure"""
    caplog.set_level(logging.INFO)
    mock_config = mock_config_factory(
        question_defaults={
            QUESTION_SELECTED_MEASURE_TYPE: MeasureType.AVERAGE,
            QUESTION_DURATION: 30,
        },
    )

    measure = _create_measure_instance(config=mock_config)
    measure.start()

    mock_average_measurement.assert_called_once_with(30)

    assert not os.path.exists(os.path.join(PROJECT_DIR, "export", "generic"))
    assert "Exporting to" not in caplog.text
    assert "Files exported to" not in caplog.text


def _create_measure_instance(config: MeasureConfig, console_events: EventGenerator | None = None):  # noqa: ANN202
    """Create instance of the Measure class"""

    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=console_events,
    )

    power_meter = DummyPowerMeter()
    return Measure(power_meter, config, render)


class SequencePowerMeter(PowerMeter):
    def __init__(self, measurements: list[PowerMeasurementResult]) -> None:
        self.measurements = measurements
        self.index = 0

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        measurement = self.measurements[self.index]
        self.index += 1
        if include_voltage:
            return measurement
        return PowerMeasurementResult(power=measurement.power, updated=measurement.updated)

    def has_voltage_support(self) -> bool:
        return True

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass


def test_ask_questions_with_no_predefined_answers(mock_config_factory: MockConfigFactory) -> None:
    """Test asking questions when no answers are predefined in config"""
    mock_config = mock_config_factory()
    measure = _create_measure_instance(config=mock_config)

    questions = [
        inquirer.Text(QUESTION_MODEL_ID, message="Specify the model identifier"),
        inquirer.Confirm(QUESTION_GZIP, message="Do you want to gzip?"),
    ]

    with patch("inquirer.prompt", return_value={QUESTION_MODEL_ID: "LCT010", QUESTION_GZIP: True}):
        answers = measure.ask_questions(questions)

    assert answers[QUESTION_MODEL_ID] == "LCT010"
    assert answers[QUESTION_GZIP] is True


def test_ask_questions_with_all_predefined_answers(mock_config_factory: MockConfigFactory) -> None:
    """Test asking questions when all answers are predefined in config"""
    mock_config = mock_config_factory(
        config_values={
            QUESTION_MODEL_ID: "LCT010",
            QUESTION_GZIP: "true",
        },
    )
    measure = _create_measure_instance(config=mock_config)

    questions = [
        inquirer.Text(QUESTION_MODEL_ID, message="Specify the model identifier"),
        inquirer.Confirm(QUESTION_GZIP, message="Do you want to gzip?"),
    ]

    answers = measure.ask_questions(questions)

    assert answers[QUESTION_MODEL_ID] == "LCT010"
    assert answers[QUESTION_GZIP] is True


def test_ask_questions_with_partial_predefined_answers(mock_config_factory: MockConfigFactory) -> None:
    """Test asking questions when only some answers are predefined in config"""
    mock_config = mock_config_factory(
        config_values={
            QUESTION_MODEL_ID: "LCT010",
        },
    )
    measure = _create_measure_instance(config=mock_config)

    questions = [
        inquirer.Text(QUESTION_MODEL_ID, message="Specify the model identifier"),
        inquirer.Confirm(QUESTION_GZIP, message="Do you want to gzip?"),
    ]

    with patch("inquirer.prompt", return_value={QUESTION_GZIP: True}):
        answers = measure.ask_questions(questions)

    assert answers[QUESTION_MODEL_ID] == "LCT010"
    assert answers[QUESTION_GZIP] is True


def test_ask_questions_with_list_type(mock_config_factory: MockConfigFactory) -> None:
    """Test asking questions that include a List question type"""
    mock_config = mock_config_factory()
    measure = _create_measure_instance(config=mock_config)

    questions = [
        inquirer.Text(QUESTION_MODEL_ID, message="Specify the model identifier"),
        inquirer.List(QUESTION_COLOR_MODE, message="Select the color mode", choices=["brightness", "hs"]),
    ]

    with patch("inquirer.prompt", return_value={QUESTION_MODEL_ID: "LCT010", QUESTION_COLOR_MODE: "brightness"}):
        answers = measure.ask_questions(questions)

    assert answers[QUESTION_MODEL_ID] == "LCT010"
    assert answers[QUESTION_COLOR_MODE] == "brightness"


def test_ask_questions_with_mode_converts_to_lut_mode_set(mock_config_factory: MockConfigFactory) -> None:
    """Test that a mode answer is converted to a set containing a LutMode"""
    mock_config = mock_config_factory(set_question_defaults=False)
    measure = _create_measure_instance(config=mock_config)

    questions = [
        inquirer.Text(QUESTION_MODE, message="Select mode"),
    ]

    with patch("inquirer.prompt", return_value={QUESTION_MODE: "hs"}):
        answers = measure.ask_questions(questions)

    assert answers[QUESTION_MODE] == {LutMode.HS}
