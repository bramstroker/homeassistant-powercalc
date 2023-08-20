import logging
import time
from datetime import datetime as dt

import config
from powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from powermeter.powermeter import PowerMeasurementResult, PowerMeter

_LOGGER = logging.getLogger("measure")


class MeasureUtil:
    def __init__(self, power_meter: PowerMeter) -> None:
        self.power_meter = power_meter

    def take_average_measurement(self, duration: int) -> float:
        """Measure average power consumption for a given time period in seconds"""
        _LOGGER.info("Measuring average power for %d seconds", duration)
        start_time = time.time()
        readings: list[float] = []
        while (time.time() - start_time) < duration:
            power = self.power_meter.get_power().power
            _LOGGER.info("Measured power: %.2f", power)
            readings.append(power)
            time.sleep(config.SLEEP_TIME)
        average = round(sum(readings) / len(readings), 2)
        _LOGGER.info("Average power: %s", average)
        return average

    def take_measurement(
        self,
        start_timestamp: float | None = None,
        retry_count: int = 0,
    ) -> float:
        """Get a measurement from the powermeter, take multiple samples and calculate the average"""
        measurements = []
        # Take multiple samples to reduce noise
        for i in range(1, config.SAMPLE_COUNT + 1):
            _LOGGER.debug("Taking sample %d", i)
            error = None
            measurement: PowerMeasurementResult | None = None
            try:
                measurement = self.power_meter.get_power()
                updated_at = dt.fromtimestamp(measurement.updated).strftime(
                    "%d-%m-%Y, %H:%M:%S",
                )
                _LOGGER.debug("Measurement received (update_time=%s)", updated_at)
            except PowerMeterError as err:
                error = err

            if measurement:
                # Check if measurement is not outdated
                if measurement.updated < start_timestamp:
                    error = OutdatedMeasurementError(
                        "Power measurement is outdated. Aborting after %d successive retries", config.MAX_RETRIES,
                    )

                # Check if we not have a 0 measurement
                if measurement.power == 0:
                    error = ZeroReadingError("0 watt was read from the power meter")

            if error:
                # Prevent endless recursion. Throw error when max retries is reached
                if retry_count == config.MAX_RETRIES:
                    raise error
                retry_count += 1
                time.sleep(config.SLEEP_TIME)
                return self.take_measurement(start_timestamp, retry_count)

            measurements.append(measurement.power)
            if config.SAMPLE_COUNT > 1:
                time.sleep(config.SLEEP_TIME_SAMPLE)

        # Determine Average PM reading
        return sum(measurements) / len(measurements)
