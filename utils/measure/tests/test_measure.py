import sys
from collections.abc import Iterator
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from inquirer import events
from inquirer.render import ConsoleRender
from measure.controller.light.const import ColorMode
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
    mock_config.set_values(
        {
            "SELECTED_DEVICE_TYPE": "Light bulb(s)",
            "COLOR_MODE": {ColorMode.BRIGHTNESS},
            "LIGHT_CONTROLLER": "dummy",
            "POWER_METER": "dummy",
            "SLEEP_TIME": 0,
            "SLEEP_INITIAL": 0,
            "RESUME": False,
        },
    )
    # def mock_config_side_effect(var: str, default: ConfigValueType | None = None, cast: int | None = None) -> ConfigValueType:
    #     values = {
    #         "SELECTED_DEVICE_TYPE": "Light bulb(s)",
    #         "COLOR_MODE": {ColorMode.BRIGHTNESS},
    #         "LIGHT_CONTROLLER": "dummy",
    #         "POWER_METER": "dummy",
    #         "SLEEP_TIME": 0,
    #         "SLEEP_INITIAL": 0,
    #         "RESUME": False,
    #     }
    #     return values.get(var, default)
    #
    # mock_config.side_effect = mock_config_side_effect

    from measure.config import SELECTED_MEASURE_TYPE

    assert SELECTED_MEASURE_TYPE == "Light bulb(s)"

    # measure = _create_measure_instance()
    # measure.start()


def _create_measure_instance(console_events: EventGenerator | None = None):  # noqa: ANN202
    from measure.measure import Measure

    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=console_events,
    )

    power_meter = DummyPowerMeter()
    return Measure(power_meter, render)
