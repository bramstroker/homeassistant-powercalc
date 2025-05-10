import logging
import time
from typing import Any

import inquirer

from measure.config import MeasureConfig
from measure.const import Trend
from measure.controller.charging.const import QUESTION_BATTERY_LEVEL_ATTRIBUTE, ChargingDeviceType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.errors import ChargingControllerError
from measure.controller.charging.factory import ChargingControllerFactory
from measure.controller.charging.hass import ATTR_BATTERY_LEVEL
from measure.runner.const import QUESTION_CHARGING_DEVICE_TYPE
from measure.runner.errors import RunnerError
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasureUtil

_LOGGER = logging.getLogger("measure")


TRICKLE_CHARGING_TIME = 1800


class ChargingRunner(MeasurementRunner):
    def __init__(self, measure_util: MeasureUtil, config: MeasureConfig) -> None:
        self.battery_level_entity: str | None = None
        self.config = config
        self.battery_level_attribute: str | None = None
        self.measure_util = measure_util
        self.controller: ChargingController = ChargingControllerFactory(config).create()
        self.charging_device_type: ChargingDeviceType | None = None

    def prepare(self, answers: dict[str, Any]) -> None:
        self.controller.process_answers(answers)

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        self.charging_device_type = ChargingDeviceType(answers[QUESTION_CHARGING_DEVICE_TYPE])
        self.battery_level_attribute = answers.get(QUESTION_BATTERY_LEVEL_ATTRIBUTE, ATTR_BATTERY_LEVEL)

        print(
            "Make sure the device is as close to 0% charged as possible before starting the test.",
        )
        input("Hit enter when you are ready to start..")

        print()

        battery_level = self.controller.get_battery_level()

        if battery_level < 100:
            self.wait_for_vacuum_to_start_charging()

        charging_measurements = self.record_charging_phase(battery_level)

        print("Done charging, start measurements for tapering phase..")

        tapering_measurements = self.record_tapering_phase()

        print("Done tapering, start measurements for trickle phase..")

        trickle_power = self.measure_util.take_average_measurement(TRICKLE_CHARGING_TIME)

        return RunnerResult(model_json_data=self._build_model_json_data(charging_measurements, trickle_power))

    def record_charging_phase(self, battery_level: int) -> dict[int, list[float]]:
        error_count = 0
        measurements: dict[int, list[float]] = {}
        while battery_level < 100:
            try:
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
                time.sleep(self.config.sleep_time)
                error_count = 0
            except ChargingControllerError as e:
                _LOGGER.error("Error during measurement: %s", e)
                error_count += 1
                if error_count > 10:
                    raise RunnerError("Too many errors occurred during measurements. aborting") from e
                time.sleep(self.config.sleep_time)
        return measurements

    def record_tapering_phase(self) -> dict[int, list[float]]:
        trend = Trend.DECREASING
        while trend != Trend.STEADY:
            measurements = [
                self.measure_util.take_measurement() for _ in range(10)
            ]
            trend = self.measure_util.calculate_trend(measurements)
            time.sleep(self.config.sleep_time)
        return {}

    def wait_for_vacuum_to_start_charging(self) -> None:
        is_charging = self.controller.is_charging()
        wait_message_printed = False
        while not is_charging:
            if not self.controller.is_valid_state():
                raise RunnerError("Device is not in a valid state.")

            if not wait_message_printed:
                print("waiting for vacuum cleaner to start charging...")
                wait_message_printed = True

            time.sleep(1)
            is_charging = self.controller.is_charging()

        if wait_message_printed:
            print("vacuum cleaner started charging, starting measurements")

    def _build_model_json_data(
        self,
        measurements: dict[int, list[float]],
        trickle_power: float
    ) -> dict:
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
