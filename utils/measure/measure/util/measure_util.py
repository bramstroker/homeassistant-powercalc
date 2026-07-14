from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime as dt
import logging
import os
from statistics import mean
import time
from typing import Protocol

from measure.const import (
    DUMMY_LOAD_MEASUREMENT_COUNT,
    DUMMY_LOAD_MEASUREMENTS_DURATION,
    PROJECT_DIR,
    RETRY_COUNT_LIMIT,
    Trend,
)
from measure.powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    UnsupportedFeatureError,
    ZeroReadingError,
)
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.tuning import MeasurementParameters

_LOGGER = logging.getLogger("measure")


class MeasurementError(PowerMeterError):
    """Base error for invalid or incomplete measurement results."""


class NoValidReadingsError(MeasurementError):
    """Raised when a measurement completes without a usable reading."""


class DummyLoadMeasurementError(MeasurementError):
    """Raised when a dummy-load measurement cannot produce a valid result."""


class MeasurementInteractionRequiredError(MeasurementError):
    """Raised when an interactive operation has no interaction adapter."""


class MeasureUtilInteraction(Protocol):
    """Input/output boundary used by optional interactive utility workflows."""

    def confirm(self, message: str) -> None: ...

    def choose(self, message: str, *, default: bool) -> bool: ...

    def notify(self, message: str) -> None: ...


class _MissingInteraction(MeasureUtilInteraction):
    def confirm(self, message: str) -> None:
        raise MeasurementInteractionRequiredError(message)

    def choose(self, message: str, *, default: bool) -> bool:
        raise MeasurementInteractionRequiredError(message)

    def notify(self, message: str) -> None:
        _LOGGER.info(message)


@dataclass(frozen=True)
class MeasurementResult:
    power: float
    voltages: list[float]


@dataclass(frozen=True)
class AverageMeasurementConvergence:
    min_duration: int
    window_duration: int
    absolute_threshold: float
    relative_threshold: float


@dataclass(frozen=True)
class AverageMeasurementSnapshot:
    elapsed: float
    average: float


@dataclass
class AverageMeasurementState:
    start_time: float
    readings: list[float]
    snapshots: list[AverageMeasurementSnapshot]
    voltages: list[float]
    consecutive_errors: int = 0


class MeasureUtil:
    def __init__(
        self,
        power_meter: PowerMeter,
        parameters: MeasurementParameters,
        include_voltage: Callable[[], bool] | None = None,
        wait: Callable[[float], None] = time.sleep,
        interaction: MeasureUtilInteraction | None = None,
    ) -> None:
        self.power_meter = power_meter
        self.dummy_load_value: float | None = None
        self.config = parameters
        self._include_voltage = include_voltage or (lambda: False)
        self._wait = wait
        self._interaction = interaction or _MissingInteraction()

    def take_average_measurement(
        self,
        duration: int,
        measure_resistance: bool = False,
        convergence: AverageMeasurementConvergence | None = None,
        on_progress: Callable[[float, float], None] | None = None,
    ) -> MeasurementResult:
        """Average valid readings, optionally as resistance, until duration or convergence."""
        _LOGGER.info("Measuring average %s over %s seconds", "resistance" if measure_resistance else "power", duration)
        state = self._collect_average_measurements(duration, measure_resistance, convergence, on_progress)
        if on_progress is not None:
            on_progress(duration, duration)

        if not state.readings:
            raise NoValidReadingsError("No valid readings were recorded")

        average = round(mean(state.readings), 2)
        _LOGGER.info(
            "Average of %d measurements: %.2f %s",
            len(state.readings),
            average,
            "Ω" if measure_resistance else "W",
        )
        return MeasurementResult(power=average, voltages=state.voltages)

    def _collect_average_measurements(
        self,
        duration: int,
        measure_resistance: bool,
        convergence: AverageMeasurementConvergence | None,
        on_progress: Callable[[float, float], None] | None = None,
    ) -> AverageMeasurementState:
        start_time = time.time()
        state = AverageMeasurementState(start_time, [], [], [])
        first_measurement = True

        while (time.time() - start_time) < duration:
            if not first_measurement and not self._sleep_before_next_average_reading(start_time, duration):
                break
            first_measurement = False
            if on_progress is not None:
                on_progress(time.time() - start_time, duration)

            try:
                result = self._take_average_measurement_reading(measure_resistance)
            except PowerMeterError as error:
                if self._average_measurement_retry_limit_reached(state, error):
                    raise
                continue

            if self._record_average_measurement_result(state, result, convergence):
                break

        return state

    def _average_measurement_retry_limit_reached(self, state: AverageMeasurementState, error: PowerMeterError) -> bool:
        state.consecutive_errors += 1
        _LOGGER.warning(
            "Error during average measurement (attempt %d/%d): %s",
            state.consecutive_errors,
            self.config.max_retries,
            error,
        )
        return state.consecutive_errors > self.config.max_retries

    def _record_average_measurement_result(
        self,
        state: AverageMeasurementState,
        result: MeasurementResult | None,
        convergence: AverageMeasurementConvergence | None,
    ) -> bool:
        if result is None:
            return False

        state.consecutive_errors = 0
        state.readings.append(result.power)
        state.voltages.extend(result.voltages)
        self._append_average_snapshot(state.start_time, state.readings, state.snapshots)
        return bool(convergence and self.average_has_converged(state.snapshots, convergence))

    @staticmethod
    def _append_average_snapshot(
        start_time: float,
        readings: list[float],
        snapshots: list[AverageMeasurementSnapshot],
    ) -> None:
        """Record the cumulative average at the current elapsed measurement time."""
        snapshots.append(
            AverageMeasurementSnapshot(
                elapsed=time.time() - start_time,
                average=mean(readings),
            ),
        )

    @staticmethod
    def average_has_converged(
        snapshots: list[AverageMeasurementSnapshot],
        convergence: AverageMeasurementConvergence,
    ) -> bool:
        """Check whether the cumulative average is stable over the configured lookback window."""
        current = snapshots[-1]
        if current.elapsed < convergence.min_duration:
            return False

        comparison_elapsed = current.elapsed - convergence.window_duration
        comparison = next(
            (snapshot for snapshot in reversed(snapshots[:-1]) if snapshot.elapsed <= comparison_elapsed),
            None,
        )
        if comparison is None:
            return False

        delta = abs(current.average - comparison.average)
        if delta <= convergence.absolute_threshold:
            _LOGGER.info(
                "Average converged after %.1f seconds: %.2f W changed %.2f W over %.1f seconds",
                current.elapsed,
                current.average,
                delta,
                convergence.window_duration,
            )
            return True

        if comparison.average == 0:
            return False

        relative_delta = delta / abs(comparison.average)
        if relative_delta <= convergence.relative_threshold:
            _LOGGER.info(
                "Average converged after %.1f seconds: %.2f W changed %.2f%% over %.1f seconds",
                current.elapsed,
                current.average,
                relative_delta * 100,
                convergence.window_duration,
            )
            return True

        return False

    def _take_average_measurement_reading(self, measure_resistance: bool) -> MeasurementResult | None:
        """Take one reading using the average-measurement mode selected for this run."""
        if measure_resistance:
            return self._take_resistance_reading()

        if self.dummy_load_value:
            return self._take_dummy_load_power_reading()

        return self._take_power_reading()

    def _sleep_before_next_average_reading(self, start_time: float, duration: int) -> bool:
        if not ((time.time() - start_time + self.config.sleep_time) < duration):
            return False
        self._wait(self.config.sleep_time)
        return True

    def _take_resistance_reading(self) -> MeasurementResult | None:
        result = self.power_meter.get_power(include_voltage=True)
        power, voltage = result.power, result.voltage

        if voltage < 1:
            raise ZeroReadingError("Voltage measurement returned zero")

        if round(power, 2) == 0:
            _LOGGER.warning("Invalid measurement: power: %.2f W, voltage: %.2f", power, voltage)
            return None

        resistance = round((voltage**2) / power, 4)
        _LOGGER.debug("Measured resistance: %.2f Ω; measured power: %.2f W, voltage: %.2f", resistance, power, voltage)
        return MeasurementResult(power=resistance, voltages=[voltage])

    def _take_dummy_load_power_reading(self) -> MeasurementResult | None:
        self._validate_voltage_support()

        result = self.power_meter.get_power(include_voltage=True)
        power, voltage = result.power, result.voltage

        if voltage < 1:
            raise ZeroReadingError("Voltage measurement returned zero")

        assert self.dummy_load_value is not None
        power -= (voltage**2) / self.dummy_load_value
        if round(power, 2) <= 0:
            _LOGGER.warning(
                "Invalid measurement after subtracting dummy load consumption. "
                "Calculated consumption: %.2f W; ignoring",
                power,
            )
            return None

        _LOGGER.info("Measured power: %.2f W", power)
        return MeasurementResult(power=power, voltages=[voltage])

    def _take_power_reading(self) -> MeasurementResult | None:
        measurement = self.power_meter.get_power(include_voltage=self._include_voltage())
        power = measurement.power
        if round(power, 2) == 0:
            _LOGGER.warning("Invalid measurement. Consumption: %.2f W; ignoring", power)
            return None
        _LOGGER.info("Measured power: %.2f W", power)
        return MeasurementResult(power=power, voltages=self._get_voltages(measurement))

    def take_measurement(
        self,
        start_timestamp: float | None = None,
        retry_count: int = 0,
    ) -> MeasurementResult:
        """Get a measurement from the powermeter, take multiple samples and calculate the average"""

        measurements: list[float] = []
        voltages: list[float] = []
        # Take multiple samples to reduce noise
        for i in range(1, self.config.sample_count + 1):
            _LOGGER.debug("Taking sample %d", i)
            measurement, error = self._get_power_measurement()
            if measurement:
                result, error = self._validate_power_measurement(measurement, start_timestamp)
                measurements.append(result.power)
                voltages.extend(result.voltages)

            if error:
                return self._retry_measurement_or_raise(error, start_timestamp, retry_count)

            if self.config.sample_count > 1:
                self._wait(self.config.sleep_time_sample)

        # Determine Average PM reading
        if not measurements:
            raise NoValidReadingsError("No valid readings were recorded")

        average = mean(measurements)
        _LOGGER.info("Average measurement: %.3f W", average)
        return MeasurementResult(power=average, voltages=voltages)

    def _get_power_measurement(self) -> tuple[PowerMeasurementResult | None, PowerMeterError | None]:
        try:
            include_voltage = self.dummy_load_value is not None or self._include_voltage()
            measurement = self.power_meter.get_power(include_voltage=include_voltage)
        except PowerMeterError as error:
            return None, error

        updated_at = dt.fromtimestamp(measurement.updated).strftime("%d-%m-%Y, %H:%M:%S")
        _LOGGER.debug("Measurement received (update_time=%s)", updated_at)
        return measurement, None

    def _validate_power_measurement(
        self,
        measurement: PowerMeasurementResult,
        start_timestamp: float | None,
    ) -> tuple[MeasurementResult, PowerMeterError | None]:
        if start_timestamp and measurement.updated < start_timestamp:
            result = MeasurementResult(power=measurement.power, voltages=self._get_voltages(measurement))
            return result, OutdatedMeasurementError(
                f"Power measurement is outdated. Aborting after {self.config.max_retries} successive retries",
            )

        power = measurement.power
        voltages = self._get_voltages(measurement)
        error: PowerMeterError | None = None
        if round(power, 2) <= 0:
            error = ZeroReadingError("0 watt was read from the power meter")

        if self.dummy_load_value:
            power, error = self._subtract_dummy_load(measurement)

        return MeasurementResult(power=power, voltages=voltages), error

    def _subtract_dummy_load(self, measurement: PowerMeasurementResult) -> tuple[float, PowerMeterError | None]:
        voltage = measurement.voltage
        if voltage < 1:
            return measurement.power, ZeroReadingError("0 Volt was read from the power meter")

        assert self.dummy_load_value is not None
        power = measurement.power - (voltage**2) / self.dummy_load_value
        if round(power, 2) <= 0:
            return power, ZeroReadingError("0 watt was read from the power meter, after subtracting the dummy load")
        return power, None

    def _retry_measurement_or_raise(
        self,
        error: PowerMeterError,
        start_timestamp: float | None,
        retry_count: int,
    ) -> MeasurementResult:
        if retry_count == self.config.max_retries:
            raise error
        if retry_count >= RETRY_COUNT_LIMIT:
            _LOGGER.error(
                "Retry count exceeded %d. Configured max_retries value: %d. Aborting to prevent infinite loop.",
                RETRY_COUNT_LIMIT,
                self.config.max_retries,
            )
            raise error
        self._wait(self.config.sleep_time)
        return self.take_measurement(start_timestamp, retry_count + 1)

    def initialize_dummy_load(self) -> float:
        """Get the previously measured dummy load resistance, or take a new measurement if it doesn't exist"""

        dummy_load_file = os.path.join(
            PROJECT_DIR,
            ".persistent/dummy_load_resistance",
        )
        if os.path.exists(dummy_load_file):
            with open(dummy_load_file) as f:
                value = float(f.read())
            _LOGGER.info("Dummy load was already measured before, value: %s Ω", value)

            self._interaction.notify("You need to preheat the dummy load so its consumption can stabilize.")
            remeasure = self._interaction.choose(
                "Remeasure the dummy load if it is not sufficiently preheated or a different load is connected?",
                default=False,
            )
            if not remeasure:
                self.dummy_load_value = value
                return self.dummy_load_value

        self._interaction.notify(
            "Use a constant resistive dummy load and connect only that load to the smart plug. "
            "Stabilization can take up to two hours.",
        )
        self._interaction.confirm("Ready to begin measuring the dummy load?")

        self.dummy_load_value = self._measure_dummy_load(dummy_load_file)
        return self.dummy_load_value

    def _measure_dummy_load(self, file_path: str) -> float:
        """Measure the dummy load and persist the value for future measurement session"""

        self._interaction.notify(
            "Measuring and checking dummy load... this will take at least %.0f minutes."
            % (DUMMY_LOAD_MEASUREMENT_COUNT / 60 * DUMMY_LOAD_MEASUREMENTS_DURATION),
        )

        # Validate power meter is capable of measuring voltage
        self._validate_voltage_support()

        while True:
            averages = [
                self.take_average_measurement(DUMMY_LOAD_MEASUREMENTS_DURATION, measure_resistance=True).power
                for _ in range(DUMMY_LOAD_MEASUREMENT_COUNT)
            ]

            trend = self._check_trend(averages)

            if not trend:
                raise DummyLoadMeasurementError("No dummy-load resistance trend could be calculated")

            if trend == Trend.STEADY:
                break

            self._interaction.notify(f"Dummy load resistance has not yet stabilized and is {trend}; repeating.")

        average = round(mean(averages), 2)

        _LOGGER.info("Dummy load measurement completed. Resistance: %s Ω", average)

        with open(file_path, "w") as f:
            f.write(str(average))
        return average

    def _check_trend(self, averages: list[float]) -> Trend | None:
        """Classify resistance readings as increasing, decreasing or steady."""
        if len(averages) < 20:
            return None

        mid = len(averages) // 2  # Calculate the midpoint

        first_half = averages[:mid]
        second_half = averages[mid:]

        first_slope = self._linear_slope(first_half)
        second_slope = self._linear_slope(second_half)

        def trend_direction(slope: float, threshold: float = 0.01) -> Trend:
            if slope > threshold:
                return Trend.INCREASING
            if slope < -threshold:
                return Trend.DECREASING
            return Trend.STEADY

        first_trend = trend_direction(first_slope)
        second_trend = trend_direction(second_slope)

        if first_trend == second_trend and first_trend != Trend.STEADY:
            return first_trend
        return Trend.STEADY

    @staticmethod
    def _linear_slope(values: list[float]) -> float:
        """Return the least-squares slope for equally spaced values without NumPy."""
        if len(values) < 2:
            return 0.0
        mean_x = (len(values) - 1) / 2
        mean_y = mean(values)
        numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
        denominator = sum((index - mean_x) ** 2 for index in range(len(values)))
        return numerator / denominator

    def _validate_voltage_support(self) -> None:
        """Check if the power meter supports voltage readings."""

        if not self.power_meter.has_voltage_support():
            raise UnsupportedFeatureError(
                "The selected power meter does not support voltage measurements required for dummy loads",
            )

    @staticmethod
    def _get_voltages(measurement: PowerMeasurementResult) -> list[float]:
        if measurement.voltage is None:
            return []
        return [measurement.voltage]
