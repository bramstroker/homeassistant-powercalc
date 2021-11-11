from __future__ import annotations

import time

from .powermeter import PowerMeasurementResult, PowerMeter


class ManualPowerMeter(PowerMeter):
    def get_power(self) -> PowerMeasurementResult:
        power = input('Input power measurement:')
        return PowerMeasurementResult(float(power), time.time())
