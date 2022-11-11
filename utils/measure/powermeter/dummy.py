from __future__ import annotations

import time

from .powermeter import PowerMeasurementResult, PowerMeter


class DummyPowerMeter:
    def get_power(self) -> PowerMeasurementResult:
        return PowerMeasurementResult(20.5, time.time())
