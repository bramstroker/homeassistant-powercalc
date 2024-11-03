import logging
import time
from typing import Any

import config
import inquirer
from controller.charging.const import QUESTION_BATTERY_LEVEL_ATTRIBUTE, ChargingDeviceType
from controller.charging.controller import ChargingController
from controller.charging.factory import ChargingControllerFactory
from util.measure_util import MeasureUtil

from .const import QUESTION_CHARGING_DEVICE_TYPE
from .errors import RunnerError
from .runner import MeasurementRunner, RunnerResult

_LOGGER = logging.getLogger("measure")


TRICKLE_CHARGING_TIME = 2


class ChargingRunner(MeasurementRunner):
    def __init__(self, measure_util: MeasureUtil) -> None:
        self.battery_level_entity: str | None = None
        self.battery_level_attribute: str | None = None
        self.measure_util = measure_util
        self.controller: ChargingController = ChargingControllerFactory().create()
        self.charging_device_type: ChargingDeviceType | None = None

    def prepare(self, answers: dict[str, Any]) -> None:
        self.controller.process_answers(answers)

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        self.charging_device_type = ChargingDeviceType(answers[QUESTION_CHARGING_DEVICE_TYPE])
        self.battery_level_attribute = answers.get(QUESTION_BATTERY_LEVEL_ATTRIBUTE)

        print(
            "Make sure the device is as close to 0% charged as possible before starting the test.",
        )
        input("Hit enter when you are ready to start..")

        battery_level = self.controller.get_battery_level()
        measurements: dict[int, list[float]] = {}

        while battery_level < 100:
            battery_level = self.controller.get_battery_level()
            is_charging = self.controller.is_charging()
            if not is_charging:
                raise RunnerError("Device is not charging anymore.")
            _LOGGER.info("Battery level: %d%%", battery_level)
            if battery_level not in measurements:
                measurements[battery_level] = []
            power = self.measure_util.take_measurement(time.time())
            _LOGGER.info("Measured power: %.2f W", power)
            measurements[battery_level].append(power)
            time.sleep(config.SLEEP_TIME)

        print("Done charging, start measurements for trickle charging..")

        trickle_power = self.measure_util.take_average_measurement(TRICKLE_CHARGING_TIME)
        measurements[100] = [trickle_power]

        return RunnerResult(model_json_data=self._build_model_json_data(measurements))

    def _build_model_json_data(self, measurements: dict[int, list[float]]) -> dict:
        """Build the model JSON data from the measurements"""
        calibrate_list = []
        for battery_level, powers in measurements.items():
            average_power = round(sum(powers) / len(powers), 2)
            calibrate_list.append(f"{battery_level} -> {average_power}")

        calculation_enabled_condition = "{{ is_state('[[entity]]', 'docked') }}"

        return {
            "device_type": self.charging_device_type.value,
            "calculation_strategy": "linear",
            "calculation_enabled_condition": calculation_enabled_condition,
            "linear_config": {
                "attribute": self.battery_level_attribute,
                "calibrate": calibrate_list,
            },
        }

    def get_questions(self) -> list[inquirer.questions.Question]:
        """Get questions to ask for the charging runner"""
        questions = [
            inquirer.List(
                name=QUESTION_CHARGING_DEVICE_TYPE,
                message="Select the charging device type",
                choices=[(charging_device_type.value, charging_device_type) for charging_device_type in ChargingDeviceType],
            ),
        ]
        questions.extend(self.controller.get_questions())
        return questions

    def measure_standby_power(self) -> float:
        return 0

    def get_export_directory(self) -> str | None:
        return "charging"
