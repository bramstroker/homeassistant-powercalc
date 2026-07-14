import logging

from measure.controller.fan.controller import FanController
from measure.execution import FanOperatingPoint, ImmediateInteraction, RunInteraction
from measure.request import FanMeasurementRequest
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasurementResult, MeasureUtil

_LOGGER = logging.getLogger("measure")

SLEEP_TIME_PERCENTAGE_CHANGE = 15


class FanRunner(MeasurementRunner[FanMeasurementRequest]):
    def __init__(
        self,
        measure_util: MeasureUtil,
        fan_controller: FanController,
        interaction: RunInteraction | None = None,
    ) -> None:
        self.measure_util = measure_util
        self.fan_controller = fan_controller
        self.interaction = interaction or ImmediateInteraction()

    def run(
        self,
        request: FanMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        measurements: dict[int, float] = {}
        voltages: list[float] = []
        for percentage in range(5, 101, 5):
            _LOGGER.info("Setting percentage to %d", percentage)
            self.fan_controller.set_percentage(percentage)
            self.interaction.operating_point(FanOperatingPoint(type="fan", percentage=percentage, on=True))
            _LOGGER.info("Waiting %d seconds to measure power", SLEEP_TIME_PERCENTAGE_CHANGE)
            self.interaction.wait(SLEEP_TIME_PERCENTAGE_CHANGE)
            result = self.measure_util.take_average_measurement(20)
            measurements[percentage] = result.power
            voltages.extend(result.voltages)

        return RunnerResult(model_json_data=self._build_model_json_data(measurements), voltages=voltages)

    @staticmethod
    def _build_model_json_data(measurements: dict) -> dict:
        calibrate_list = [f"{percentage} -> {power:.2f}" for percentage, power in measurements.items()]

        return {
            "device_type": "fan",
            "calculation_strategy": "linear",
            "linear_config": {"calibrate": calibrate_list},
        }

    def measure_standby_power(self) -> MeasurementResult:
        _LOGGER.info("Turning off fan to start measuring standby power")
        self.fan_controller.turn_off()
        self.interaction.operating_point(FanOperatingPoint(type="fan", percentage=0, on=False))
        _LOGGER.info("Waiting %d seconds to measure power", SLEEP_TIME_PERCENTAGE_CHANGE)
        self.interaction.wait(SLEEP_TIME_PERCENTAGE_CHANGE)
        return self.measure_util.take_average_measurement(20)
