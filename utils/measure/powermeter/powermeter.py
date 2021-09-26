from __future__ import annotations

import time
from typing import NamedTuple


class PowerMeter:
    def get_power(self) -> PowerMeasurementResult:
        pass

    def get_questions(self) -> list[dict]:
        return []

    def process_answers(self, answers):
        pass


class PowerMeasurementResult(NamedTuple):
    power: float
    updated: float
