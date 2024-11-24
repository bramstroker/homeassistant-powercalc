import sys
from collections.abc import Iterator
from io import StringIO
from unittest.mock import patch

from inquirer import events
from inquirer.render import ConsoleRender
from measure.measure import Measure
from measure.powermeter.dummy import DummyPowerMeter
from readchar import key


class EventGenerator:
    def __init__(self, *args: str) -> None:
        self.iterator: Iterator[str] = args.__iter__()

    def next(self) -> events.KeyPressed:
        return events.KeyPressed(next(self.iterator))


def event_factory(*args: str) -> EventGenerator:
    return EventGenerator(*args)


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


@patch("measure.config.config")
def test_2(mock_config) -> None:
    def mock_config_side_effect(key: str, default=None):
        values = {
            "SELECTED_MEASURE_TYPE": "Light bulb(s)",
            "COLOR_MODE": "color_temp",
        }
        return values.get(key, default)

    mock_config.side_effect = mock_config_side_effect

    from measure.config import SELECTED_MEASURE_TYPE

    assert SELECTED_MEASURE_TYPE == "sqlite://:memory:"

    # os.environ["SELECTED_DEVICE_TYPE"] = "Light bulb(s)"
    # os.environ["COLOR_MODE"] = "color_temp"
    # os.environ["GENERATE_MODEL_JSON"] = "true"
    # os.environ["GZIP"] = "true"
    # os.environ["MULTIPLE_LIGHTS"] = "false"
    # os.environ["LIGHT_ENTITY_ID"] = "xx"
    # os.environ["MEASURE_DEVICE"] = "Shelly Plug S"
    # os.environ["NUM_LIGHTS"] = "1"
    # os.environ["LIGHT_MODEL_ID"] = "xx"
    # os.environ["MODEL_NAME"] = "xx"
    # os.environ["DUMMY_LOAD"] = "true"
    # os.environ["POWERMETER_ENTITY_ID"] = "sensor.my_power"
    # os.environ["RESUME"] = "true"

    measure = _create_measure_instance()

    # with patch("builtins.input", return_value=""):
    measure.start()


def _create_measure_instance(console_events: EventGenerator | None = None) -> Measure:
    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=console_events,
    )

    power_meter = DummyPowerMeter()
    return Measure(power_meter, render)
