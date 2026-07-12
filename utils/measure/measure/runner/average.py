import logging
from typing import Any

import inquirer

from measure.execution import RunInteraction
from measure.interactions import ConsoleInteraction
from measure.util.measure_util import MeasurementResult, MeasureUtil

from .const import QUESTION_DURATION
from .runner import MeasurementRunner, RunnerResult

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


class AverageRunner(MeasurementRunner):
    def __init__(
        self,
        measure_util: MeasureUtil,
        duration: int = 60,
        interaction: RunInteraction | None = None,
    ) -> None:
        self.measure_util = measure_util
        self.duration = duration
        self.interaction = interaction or ConsoleInteraction()

    def prepare(self, answers: dict[str, Any]) -> None:
        self.duration = int(answers[QUESTION_DURATION])

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        self.interaction.confirm("Ready to start the average measurement.")

        result = self.measure_util.take_average_measurement(self.duration)

        return RunnerResult(model_json_data={}, voltages=result.voltages)

    def get_questions(self) -> list[inquirer.questions.Question]:
        return [
            inquirer.Text(
                name=QUESTION_DURATION,
                message="For how long do you want to measure? In seconds",
            ),
        ]

    def measure_standby_power(self) -> MeasurementResult:
        return MeasurementResult(power=0, voltages=[])
