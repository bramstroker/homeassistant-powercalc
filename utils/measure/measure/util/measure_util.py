import logging
import os
import time
from datetime import datetime as dt

from measure.config import MeasureConfig
from measure.const import PROJECT_DIR
from measure.powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter

_LOGGER = logging.getLogger("measure")


class MeasureUtil:
    def __init__(self, power_meter: PowerMeter, config: MeasureConfig) -> None:
        self.power_meter = power_meter
        self.dummy_load_value: float | None = None
        self.config = config

    def take_average_measurement(self, duration: int) -> float:
        """Measure average power consumption for a given time period in seconds"""
        _LOGGER.info("Measuring average power for %d seconds", duration)
        start_time = time.time()
        readings: list[float] = []
        while (time.time() - start_time) < duration:
            power = self.power_meter.get_power().power
            _LOGGER.info("Measured power: %.2f", power)
            readings.append(power)
            time.sleep(self.config.sleep_time)
        average = round(sum(readings) / len(readings), 2)
        if self.dummy_load_value:
            average -= self.dummy_load_value

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
        for i in range(1, self.config.sample_count + 1):
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
                        "Power measurement is outdated. Aborting after %d successive retries",
                        self.config.max_retries,
                    )

                # Check if we not have a 0 measurement
                if measurement.power == 0:
                    error = ZeroReadingError("0 watt was read from the power meter")

            if error:
                # Prevent endless recursion. Throw error when max retries is reached
                if retry_count == self.config.max_retries:
                    raise error
                retry_count += 1
                time.sleep(self.config.sleep_time)
                return self.take_measurement(start_timestamp, retry_count)

            measurements.append(measurement.power)
            if self.config.sample_count > 1:
                time.sleep(self.config.sleep_time_sample)

        # Determine Average PM reading
        average = sum(measurements) / len(measurements)
        if self.dummy_load_value:
            average -= self.dummy_load_value
        return average

    def initialize_dummy_load(self) -> float:
        """Get the previously measured dummy load value, or take a new measurement if it doesn't exist"""

        dummy_load_file = os.path.join(
            PROJECT_DIR,
            ".persistent/dummy_load",
        )
        if os.path.exists(dummy_load_file):
            with open(dummy_load_file) as f:
                value = float(f.read())
            _LOGGER.info("Dummy load was already measured before, value: %sW", value)

            inquirer = input("Do you want to measure the dummy load again? (y/n): ")
            if inquirer.lower() == "n":
                self.dummy_load_value = value
                return self.dummy_load_value

        self.dummy_load_value = self._measure_dummy_load(dummy_load_file)
        return self.dummy_load_value

    def _measure_dummy_load(self, file_path: str) -> float:
        """Measure the dummy load and persist the value for future measurement session"""
        print()
        print("Tip: Use a dummy load with constant power consumption. Stick to resistive loads for the best results!")
        print("Important: Connect only the dummy load to your smart plug—not the device you're measuring.")
        print("Preheat your dummy load until its temperature stabilizes. This usually takes about 2 hours.")
        input("Ready to start? Press Enter to begin measuring the dummy load!")
        average = self.take_average_measurement(1)
        with open(file_path, "w") as f:
            f.write(str(average))
        return average
