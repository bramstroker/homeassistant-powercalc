from __future__ import annotations

import time

from .powermeter import PowerMeasurementResult, PowerMeter


class ManualPowerMeter(PowerMeter):
    def get_power(self) -> PowerMeasurementResult:
        print('Input power measurement:')
        power = input()
        return PowerMeasurementResult(float(power), time.time())
