from __future__ import annotations

import time
from typing import Any

from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class ManualPowerMeter(PowerMeter):
    def get_power(self) -> PowerMeasurementResult:
        power = input("Input power measurement:")
        return PowerMeasurementResult(float(power), time.time())

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
