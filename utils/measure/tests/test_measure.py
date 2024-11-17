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


def test_measure() -> None:
    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=event_factory(
            key.ENTER,  # MEASURE_TYPE
            "n",  # DUMMY_LOAD
            "y",  # GENERATE_MODEL_JSON
            key.ENTER,  # COLOR_MODE
            key.ENTER,  # GZIP
            "n",  # MULTIPLE_LIGHTS
        ),
    )

    power_meter = DummyPowerMeter()
    measure = Measure(power_meter, console_render=render)

    with patch("builtins.input", return_value=""):
        measure.start()
