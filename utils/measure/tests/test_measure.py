import os
import sys
from io import StringIO
from unittest.mock import patch

from inquirer import events
from inquirer.render import ConsoleRender
from readchar import key

from ..measure import Measure
from ..powermeter.dummy import DummyPowerMeter


class Iterable:
    def __init__(self, *args):
        self.iterator = args.__iter__()

    def next(self):
        return events.KeyPressed(next(self.iterator))


def event_factory(*args):
    return Iterable(*args)


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


def test_2() -> None:
    os.environ["SELECTED_DEVICE_TYPE"] = "Light bulb(s)"
    os.environ["COLOR_MODE"] = "color_temp"
    os.environ["GENERATE_MODEL_JSON"] = "true"
    os.environ["GZIP"] = "true"
    os.environ["MULTIPLE_LIGHTS"] = "false"
    os.environ["LIGHT_ENTITY_ID"] = "xx"
    os.environ["MEASURE_DEVICE"] = "Shelly Plug S"
    os.environ["NUM_LIGHTS"] = "1"
    os.environ["LIGHT_MODEL_ID"] = "xx"
    os.environ["MODEL_NAME"] = "xx"
    os.environ["DUMMY_LOAD"] = "true"
    os.environ["POWERMETER_ENTITY_ID"] = "sensor.my_power"
    os.environ["RESUME"] = "true"

    measure = _create_measure_instance()

    with patch("builtins.input", return_value=""):
        measure.start()


def _create_measure_instance(console_events: Iterable | None = None) -> Measure:
    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=console_events,
    )

    power_meter = DummyPowerMeter()
    return Measure(power_meter, render)
