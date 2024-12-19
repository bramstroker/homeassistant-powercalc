from __future__ import annotations

import time
from typing import Any

from measure.powermeter.powermeter import ExtendedPowerMeasurementResult, PowerMeasurementResult, PowerMeter


class DummyPowerMeter(PowerMeter):
    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult | ExtendedPowerMeasurementResult:
        if include_voltage:
            return ExtendedPowerMeasurementResult(20.5, 233.0, time.time())
        return PowerMeasurementResult(20.5, time.time())

    def has_voltage_support(self) -> bool:
        return True

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
