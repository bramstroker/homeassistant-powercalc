import csv
import logging
import time
from typing import Any

import inquirer

from measure.config import MeasureConfig
from measure.runner.const import QUESTION_EXPORT_FILENAME
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasureUtil

INTERVAL = 2

_LOGGER = logging.getLogger("measure")

DEFAULT_FILENAME = "record.csv"


class RecorderRunner(MeasurementRunner):
    def __init__(self, measure_util: MeasureUtil, config: MeasureConfig) -> None:
        self.measure_util = measure_util
        self.config = config
        self.filename = DEFAULT_FILENAME

    def prepare(self, answers: dict[str, Any]) -> None:
        self.filename = answers[QUESTION_EXPORT_FILENAME]

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        input("Press Enter to start and CTRL+C to stop")

        try:
            csv_filepath = f"{export_directory}/{self.filename}"
            start_time = time.time()
            with open(csv_filepath, "w", newline="") as csv_file:
                writer = csv.writer(csv_file)
                while True:
                    timestamp = time.time()
                    print("Measurement")
                    measurement = self.measure_util.take_measurement(timestamp)
                    _LOGGER.info("Measurement %.2f", measurement)
                    writer.writerow([timestamp - start_time, measurement])
                    time.sleep(INTERVAL)
        except KeyboardInterrupt:
            _LOGGER.info("Stopped recording")

        return RunnerResult(model_json_data={})

    def get_questions(self) -> list[inquirer.questions.Question]:
        return [
            inquirer.Text(
                name=QUESTION_EXPORT_FILENAME,
                message="To which file do you want to export?",
                default=DEFAULT_FILENAME,
            ),
        ]

    def measure_standby_power(self) -> float:
        return 0

    def get_export_directory(self) -> str:
        return "recorder"
