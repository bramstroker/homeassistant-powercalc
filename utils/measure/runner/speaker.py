import logging
import time
from typing import Any

import config
import inquirer
from measure_util import MeasureUtil
from media_controller.controller import MediaController
from media_controller.factory import MediaControllerFactory
from powermeter.errors import ZeroReadingError

from .runner import MeasurementRunner, RunnerResult

DURATION_PER_VOLUME_LEVEL = 20
STREAM_URL = "https://assets.ctfassets.net/4zjnzn055a4v/5d3omOpQeliAWkVm1QmZBj/308d35fbb226a4643aeb7b132949dbd3/g_pink.mp3"
SLEEP_PRE_MEASURE = 2
SLEEP_MUTE = 5

_LOGGER = logging.getLogger("measure")


class SpeakerRunner(MeasurementRunner):
    def __init__(self):
        self.measure_util: MeasureUtil = MeasureUtil()
        self.media_controller: MediaController = MediaControllerFactory().create()
        pass

    def prepare(self, answers: dict[str, Any]) -> None:
        self.media_controller.process_answers(answers)

    def run(
        self, answers: dict[str, Any], export_directory: str
    ) -> RunnerResult | None:
        summary = {}
        duration = DURATION_PER_VOLUME_LEVEL

        print(
            f"Prepare to start measuring the power for {duration} seconds on each volume level starting with 10 until 100 (with steps of 10 between)"
        )
        print(
            "WARNING: during the measurement session the volume will be increased to the maximum, which can be harmful for your ears"
        )
        input("Hit enter when you are ready to start..")

        for volume in range(10, 101, 10):
            _LOGGER.info(f"Setting volume to {volume}")
            self.media_controller.set_volume(volume)
            _LOGGER.info("Start streaming noise")
            self.media_controller.play_audio(STREAM_URL)
            time.sleep(SLEEP_PRE_MEASURE)
            summary[volume] = self.measure_util.take_average_measurement(duration)

        _LOGGER.info(f"Muting volume and waiting for {SLEEP_MUTE} seconds")
        time.sleep(SLEEP_MUTE)
        summary[0] = self.measure_util.take_average_measurement(duration)

        self.media_controller.set_volume(10)

        print("Summary of all average measurements:")
        for volume in summary:
            print(volume, " : ", summary[volume])

        return RunnerResult(model_json_data=self._build_model_json_data(summary))

    @staticmethod
    def _build_model_json_data(summary: dict) -> dict:
        calibrate_list = []
        for volume in summary:
            calibrate_list.append(f"{volume} -> {summary[volume]}")

        return {
            "device_type": "smart_speaker",
            "supported_modes": ["linear"],
            "calculation_enabled_condition": "{{ is_state('[[entity]]', 'playing') }}",
            "linear_config": {"calibrate": calibrate_list},
        }

    def get_questions(self) -> list[inquirer.questions.Question]:
        return self.media_controller.get_questions()

    def measure_standby_power(self) -> float:
        self.media_controller.turn_off()
        start_time = time.time()
        _LOGGER.info(
            f"Measuring standby power. Waiting for {config.SLEEP_STANDBY} seconds..."
        )
        time.sleep(config.SLEEP_STANDBY)
        try:
            return self.measure_util.take_measurement(start_time)
        except ZeroReadingError:
            _LOGGER.error("Measured 0 watt as standby power.")
            return 0

    def get_export_directory(self) -> str:
        return "speaker"
