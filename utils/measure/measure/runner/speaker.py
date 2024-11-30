import logging
import time
from typing import Any

import inquirer

from measure.config import MeasureConfig
from measure.controller.media.controller import MediaController
from measure.controller.media.factory import MediaControllerFactory
from measure.powermeter.errors import ZeroReadingError
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasureUtil

DURATION_PER_VOLUME_LEVEL = 20
STREAM_URL = "https://powercalc.s3.eu-west-1.amazonaws.com/g_pink.mp3"
SLEEP_PRE_MEASURE = 2
SLEEP_MUTE = 5

_LOGGER = logging.getLogger("measure")


class SpeakerRunner(MeasurementRunner):
    def __init__(self, measure_util: MeasureUtil, config: MeasureConfig) -> None:
        self.measure_util = measure_util
        self.config = config
        self.media_controller: MediaController = MediaControllerFactory(config).create()

    def prepare(self, answers: dict[str, Any]) -> None:
        self.media_controller.process_answers(answers)

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        summary = {}
        duration = DURATION_PER_VOLUME_LEVEL

        print(
            f"Prepare to start measuring the power for {duration} seconds on each volume level starting with 10 until 100 (with steps of 10 between)",
        )
        print(
            "WARNING: during the measurement session the volume will be increased to the maximum, which can be harmful for your ears",
        )
        input("Hit enter when you are ready to start..")

        for volume in range(10, 101, 10):
            _LOGGER.info("Setting volume to %d", volume)
            self.media_controller.set_volume(volume)
            _LOGGER.info("Start streaming noise")
            self.media_controller.play_audio(STREAM_URL)
            time.sleep(SLEEP_PRE_MEASURE)
            summary[volume] = self.measure_util.take_average_measurement(duration)

        _LOGGER.info("Muting volume and waiting for %d seconds", SLEEP_MUTE)
        time.sleep(SLEEP_MUTE)
        summary[0] = self.measure_util.take_average_measurement(duration)

        self.media_controller.set_volume(10)

        print("Summary of all average measurements:")
        for volume in summary:
            print(volume, " : ", summary[volume])

        return RunnerResult(model_json_data=self._build_model_json_data(summary))

    @staticmethod
    def _build_model_json_data(summary: dict) -> dict:
        calibrate_list = [f"{volume} -> {summary[volume]}" for volume in summary]

        return {
            "device_type": "smart_speaker",
            "calculation_strategy": "linear",
            "calculation_enabled_condition": "{{ is_state('[[entity]]', 'playing') }}",
            "linear_config": {"calibrate": calibrate_list},
        }

    def get_questions(self) -> list[inquirer.questions.Question]:
        return self.media_controller.get_questions()

    def measure_standby_power(self) -> float:
        self.media_controller.turn_off()
        start_time = time.time()
        _LOGGER.info(
            "Measuring standby power. Waiting for %d seconds...",
            self.config.sleep_standby,
        )
        time.sleep(self.config.sleep_standby)
        try:
            return self.measure_util.take_measurement(start_time)
        except ZeroReadingError:
            _LOGGER.error("Measured 0 watt as standby power.")
            return 0

    def get_export_directory(self) -> str | None:
        return "speaker"
