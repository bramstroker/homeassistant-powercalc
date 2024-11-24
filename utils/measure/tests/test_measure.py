import sys
from collections.abc import Iterator
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from inquirer import events
from inquirer.render import ConsoleRender

from measure.config import MeasureConfig
from measure.powermeter.dummy import DummyPowerMeter
from readchar import key


class EventGenerator:
    def __init__(self, *args: str) -> None:
        self.iterator: Iterator[str] = args.__iter__()

    def next(self) -> events.KeyPressed:
        return events.KeyPressed(next(self.iterator))


def event_factory(*args: str) -> EventGenerator:
    return EventGenerator(*args)


@pytest.fixture(autouse=True)
def reload_measure_module():
    # importlib.reload(measure)
    # importlib.reload(decouple)
    yield


def test_wizard() -> None:
    measure = _create_measure_instance(
        event_factory(
            key.ENTER,  # MEASURE_TYPE
            "n",  # DUMMY_LOAD
            "y",  # GENERATE_MODEL_JSON
            key.ENTER,  # COLOR_MODE
            key.ENTER,  # GZIP
            "n",  # MULTIPLE_LIGHTS
        ),
    )

    with patch("builtins.input", return_value=""):
        measure.start()


def test_light_run(mock_config: MagicMock) -> None:
    mock_config.selected_measure_type = "Light bulb(s)"
    mock_config.color_mode = {"brightness"}
    mock_config.selected_light_controller = "dummy"
    mock_config.power_meter = "dummy"
    mock_config.sleep_time = 0
    mock_config.sleep_initial = 0
    mock_config.resume = False

    measure = _create_measure_instance(config=mock_config)
    measure.start()


def _create_measure_instance(config: MeasureConfig | None = None, console_events: EventGenerator | None = None):  # noqa: ANN202
    from measure.measure import Measure

    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=console_events,
    )

    power_meter = DummyPowerMeter()
    return Measure(power_meter, config, render)
