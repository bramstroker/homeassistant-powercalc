from __future__ import annotations

import time

from .powermeter import PowerMeasurementResult, PowerMeter


class DummyPowerMeter(PowerMeter):
    def get_power(self) -> PowerMeasurementResult:
        return PowerMeasurementResult(20.5, time.time())
