import logging
import time

from measure.controller.charging.const import ATTR_BATTERY_LEVEL, ChargingDeviceType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.errors import ChargingControllerError
from measure.execution import ImmediateInteraction, RunInteraction
from measure.request import ChargingMeasurementRequest
from measure.runner.errors import RunnerError
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.tuning import MeasurementParameters
from measure.util.measure_util import MeasurementResult, MeasureUtil

_LOGGER = logging.getLogger("measure")


TRICKLE_CHARGING_TIME = 1800


class ChargingRunner(MeasurementRunner[ChargingMeasurementRequest]):
    def __init__(
        self,
        measure_util: MeasureUtil,
        parameters: MeasurementParameters,
        controller: ChargingController,
        interaction: RunInteraction | None = None,
        battery_level_attribute: str | None = ATTR_BATTERY_LEVEL,
    ) -> None:
        self.battery_level_entity: str | None = None
        self.config = parameters
        self.battery_level_attribute = battery_level_attribute
        self.measure_util = measure_util
        self.controller = controller
        self.charging_device_type: ChargingDeviceType | None = None
        self.interaction = interaction or ImmediateInteraction()

    def run(
        self,
        request: ChargingMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        self.charging_device_type = request.charging_device_type

        self.interaction.notify(
            "Make sure the device is as close to 0% charged as possible before starting the test.",
        )
        self.interaction.confirm("Ready to start charging measurement.")

        battery_level = self.controller.get_battery_level()
        measurements: dict[int, list[float]] = {}
        voltages: list[float] = []

        if battery_level < 100:
            self.wait_for_vacuum_to_start_charging()

        error_count = 0
        while battery_level < 100:
            try:
                battery_level = self.controller.get_battery_level()
                is_charging = self.controller.is_charging()
                if not is_charging:
                    raise RunnerError("Device is not charging anymore.")
                _LOGGER.info("Battery level: %d%%", battery_level)
                if battery_level not in measurements:
                    measurements[battery_level] = []
                result = self.measure_util.take_measurement(time.time())
                _LOGGER.info("Measured power: %.2f W", result.power)
                measurements[battery_level].append(result.power)
                voltages.extend(result.voltages)
                self.interaction.wait(self.config.sleep_time)
                error_count = 0
            except ChargingControllerError as e:
                _LOGGER.error("Error during measurement: %s", e)
                error_count += 1
                if error_count > 10:
                    raise RunnerError("Too many errors occurred during measurements. aborting") from e
                self.interaction.wait(self.config.sleep_time)

        self.interaction.notify("Done charging, start measurements for trickle charging..")

        trickle_result = self.measure_util.take_average_measurement(TRICKLE_CHARGING_TIME)
        measurements[100] = [trickle_result.power]
        voltages.extend(trickle_result.voltages)

        return RunnerResult(model_json_data=self._build_model_json_data(measurements), voltages=voltages)

    def wait_for_vacuum_to_start_charging(self) -> None:
        is_charging = self.controller.is_charging()
        wait_message_printed = False
        while not is_charging:
            if not self.controller.is_valid_state():
                raise RunnerError("Device is not in a valid state.")

            if not wait_message_printed:
                self.interaction.notify("Waiting for charging device to start charging...")
                wait_message_printed = True

            self.interaction.wait(1)
            is_charging = self.controller.is_charging()

        if wait_message_printed:
            self.interaction.notify("Charging device started charging, starting measurements")

    def _build_model_json_data(self, measurements: dict[int, list[float]]) -> dict:
        """Build the model JSON data from the measurements"""
        if self.charging_device_type is None:
            raise RuntimeError("Charging runner is not configured")
        calibrate_list = []
        for battery_level, powers in measurements.items():
            average_power = round(sum(powers) / len(powers), 2)
            calibrate_list.append(f"{battery_level} -> {average_power}")

        calculation_enabled_condition = "{{ is_state('[[entity]]', 'docked') }}"

        linear_config: dict[str, object] = {"calibrate": calibrate_list}
        if self.battery_level_attribute is not None:
            linear_config["attribute"] = self.battery_level_attribute

        return {
            "device_type": self.charging_device_type.value,
            "calculation_strategy": "linear",
            "calculation_enabled_condition": calculation_enabled_condition,
            "linear_config": linear_config,
        }

    def measure_standby_power(self) -> MeasurementResult:
        return MeasurementResult(power=0, voltages=[])
