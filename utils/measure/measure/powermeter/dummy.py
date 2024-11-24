from __future__ import annotations

import time
from typing import Any

from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class DummyPowerMeter(PowerMeter):
    def get_power(self) -> PowerMeasurementResult:
        return PowerMeasurementResult(20.5, time.time())

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
