import os
import sys
from collections.abc import Iterator
from io import StringIO
from unittest.mock import patch

from inquirer import events
from inquirer.render import ConsoleRender
from measure.config import MeasureConfig
from measure.const import PROJECT_DIR
from measure.powermeter.dummy import DummyPowerMeter
from readchar import key


class EventGenerator:
    def __init__(self, *args: str) -> None:
        self.iterator: Iterator[str] = args.__iter__()

    def next(self) -> events.KeyPressed:
        return events.KeyPressed(next(self.iterator))


def event_factory(*args: str) -> EventGenerator:
    return EventGenerator(*args)


def test_wizard(mock_config_factory) -> None:  # noqa: ANN001
    mock_config = mock_config_factory(
        set_question_defaults=False,
    )
    measure = _create_measure_instance(
        mock_config,
        console_events=event_factory(
            key.ENTER,  # MEASURE_TYPE
            "n",  # DUMMY_LOAD
            "y",  # GENERATE_MODEL_JSON
            key.DOWN,  # COLOR_MODE
            key.DOWN,
            key.ENTER,
            key.ENTER,  # GZIP
            "n",  # MULTIPLE_LIGHTS
        ),
    )

    with patch("builtins.input", return_value=""):
        measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/dummy/brightness.csv.gz"))
    assert not os.path.exists(os.path.join(PROJECT_DIR, "export/dummy/model.json"))


def test_light_run_brightness(mock_config_factory) -> None:  # noqa: ANN001
    mock_config = mock_config_factory()

    measure = _create_measure_instance(config=mock_config)
    measure.start()

    assert os.path.exists(os.path.join(PROJECT_DIR, "export/dummy/brightness.csv.gz"))
    assert os.path.exists(os.path.join(PROJECT_DIR, "export/dummy/model.json"))


def _create_measure_instance(config: MeasureConfig, console_events: EventGenerator | None = None):  # noqa: ANN202
    from measure.measure import Measure

    sys.stdin = StringIO()
    sys.stdout = StringIO()

    render = ConsoleRender(
        event_generator=console_events,
    )

    power_meter = DummyPowerMeter()
    return Measure(power_meter, config, render)
