import logging
from typing import Any

import inquirer

from measure.util.measure_util import MeasureUtil

from .const import QUESTION_DURATION
from .runner import MeasurementRunner, RunnerResult

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


class AverageRunner(MeasurementRunner):
    def __init__(self, measure_util: MeasureUtil, duration: int = 60) -> None:
        self.measure_util = measure_util
        self.duration = duration

    def prepare(self, answers: dict[str, Any]) -> None:
        self.duration = int(answers[QUESTION_DURATION])

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        input("Press enter to start")

        self.measure_util.take_average_measurement(self.duration)

        return RunnerResult(model_json_data={})

    def get_questions(self) -> list[inquirer.questions.Question]:
        return [
            inquirer.Text(
                name=QUESTION_DURATION,
                message="For how long do you want to measure? In seconds",
            ),
        ]

    def measure_standby_power(self) -> float:
        return 0
