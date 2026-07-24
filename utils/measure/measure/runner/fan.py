import logging
import time

from measure.controller.fan.controller import FanController
from measure.execution import FanOperatingPoint, ImmediateInteraction, RunInteraction
from measure.request import FanMeasurementRequest
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasurementResult, MeasureUtil

_LOGGER = logging.getLogger("measure")

SLEEP_TIME_PERCENTAGE_CHANGE = 15
MEASURE_DURATION_PER_STEP = 20
FAST_TEST_PERCENTAGES = (5, 100)


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
        percentages = FAST_TEST_PERCENTAGES if request.fast_test_mode else tuple(range(5, 101, 5))
        total_steps = len(percentages)
        self.interaction.progress(
            0,
            total_steps,
            phase="Measuring fan speeds",
            remaining_seconds=self._remaining_seconds(0, request.fast_test_mode),
        )
        for completed_steps, percentage in enumerate(percentages, start=1):
            _LOGGER.info("Setting percentage to %d", percentage)
            self.fan_controller.set_percentage(percentage)
            self.interaction.operating_point(FanOperatingPoint(type="fan", percentage=percentage, on=True))
            self.interaction.phase(f"Stabilizing fan at {percentage}%")
            if not request.fast_test_mode:
                _LOGGER.info("Waiting %d seconds to measure power", SLEEP_TIME_PERCENTAGE_CHANGE)
                self.interaction.wait(SLEEP_TIME_PERCENTAGE_CHANGE)
            self.interaction.phase(f"Measuring fan at {percentage}%")
            result = (
                self.measure_util.take_measurement(time.time())
                if request.fast_test_mode
                else self.measure_util.take_average_measurement(MEASURE_DURATION_PER_STEP)
            )
            measurements[percentage] = result.power
            voltages.extend(result.voltages)
            self.interaction.progress(
                completed_steps,
                total_steps,
                phase="Measuring fan speeds",
                remaining_seconds=self._remaining_seconds(completed_steps, request.fast_test_mode),
            )

        return RunnerResult(model_json_data=self._build_model_json_data(measurements), voltages=voltages)

    @staticmethod
    def _remaining_seconds(completed_steps: int, fast_test_mode: bool = False) -> float:
        """Estimated time for the remaining fan-speed steps."""
        if fast_test_mode:
            return 0
        return (20 - completed_steps) * (SLEEP_TIME_PERCENTAGE_CHANGE + MEASURE_DURATION_PER_STEP)

    @staticmethod
    def _build_model_json_data(measurements: dict[int, float]) -> dict[str, object]:
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
        if self.measure_util.config.fast_test_mode:
            return self.measure_util.take_measurement(time.time())
        _LOGGER.info("Waiting %d seconds to measure power", SLEEP_TIME_PERCENTAGE_CHANGE)
        self.interaction.wait(SLEEP_TIME_PERCENTAGE_CHANGE)
        return self.measure_util.take_average_measurement(MEASURE_DURATION_PER_STEP)

    def cleanup(self) -> None:
        """Turn off the fan after success, failure, or cancellation."""

        try:
            self.fan_controller.turn_off()
        except Exception:  # noqa: BLE001 - cleanup must not mask the measurement outcome
            _LOGGER.warning("Could not turn off fan during cleanup", exc_info=True)
