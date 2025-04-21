import logging
import time
from typing import Any

import inquirer

from measure.config import MeasureConfig
from measure.controller.fan.controller import FanController
from measure.controller.fan.factory import FanControllerFactory
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasureUtil

_LOGGER = logging.getLogger("measure")

SLEEP_TIME_PERCENTAGE_CHANGE = 15


class FanRunner(MeasurementRunner):
    def __init__(self, measure_util: MeasureUtil, config: MeasureConfig) -> None:
        self.measure_util = measure_util
        self.config = config
        self.fan_controller: FanController = FanControllerFactory(config).create()

    def prepare(self, answers: dict[str, Any]) -> None:
        self.fan_controller.process_answers(answers)

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        measurements: dict[int, float] = {}
        for percentage in range(5, 101, 5):
            _LOGGER.info("Setting percentage to %d", percentage)
            self.fan_controller.set_percentage(percentage)
            _LOGGER.info("Waiting %d seconds to measure power", SLEEP_TIME_PERCENTAGE_CHANGE)
            time.sleep(SLEEP_TIME_PERCENTAGE_CHANGE)
            measurements[percentage] = self.measure_util.take_average_measurement(20)

        return RunnerResult(model_json_data=self._build_model_json_data(measurements))

    @staticmethod
    def _build_model_json_data(measurements: dict) -> dict:
        calibrate_list = [f"{percentage} -> {power:.2f}" for percentage, power in measurements.items()]

        return {
            "device_type": "fan",
            "calculation_strategy": "linear",
            "linear_config": {"calibrate": calibrate_list},
        }

    def get_questions(self) -> list[inquirer.questions.Question]:
        return self.fan_controller.get_questions()

    def measure_standby_power(self) -> float:
        _LOGGER.info("Turning off fan to start measuring standby power")
        self.fan_controller.turn_off()
        _LOGGER.info("Waiting %d seconds to measure power", SLEEP_TIME_PERCENTAGE_CHANGE)
        time.sleep(SLEEP_TIME_PERCENTAGE_CHANGE)
        return self.measure_util.take_average_measurement(20)
