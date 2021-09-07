from __future__ import annotations

import time
from .powermeter import PowerMeasurementResult, PowerMeter


class ZwaveJsPowerMeter(PowerMeter):
    def __init__(self, ws_url: str):
        self._ws_url = ws_url

    def get_power(self) -> PowerMeasurementResult:
        return PowerMeasurementResult(
            0,
            time.time()
        )

    def get_questions(self) -> list[dict]:
        return [
        ]

    def process_answers(self, answers):
        self._node_id = answers["powermeter_zwave_node_id"]
