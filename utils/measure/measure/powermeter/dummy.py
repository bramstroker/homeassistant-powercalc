from __future__ import annotations

import random
import time

from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class DummyPowerMeter(PowerMeter):
    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        power = round(random.uniform(0, 100), 2)  # noqa: S311  # synthetic dummy readings, not security-sensitive
        if include_voltage:
            return PowerMeasurementResult(
                power=power,
                voltage=233.0,
                updated=time.time(),
            )
        return PowerMeasurementResult(power=power, updated=time.time())

    def has_voltage_support(self) -> bool:
        return True
