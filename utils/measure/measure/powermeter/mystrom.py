from __future__ import annotations

import time
from typing import Any

import requests

from measure.powermeter.errors import PowerMeterError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class MyStromPowerMeter(PowerMeter):
    def __init__(self, device_ip: str) -> None:
        self._device_ip = device_ip

    def get_power(self) -> PowerMeasurementResult:
        r = requests.get(
            f"http://{self._device_ip}/report",
            timeout=10,
        )
        json = r.json()

        try:
            power = json["power"]
        except KeyError as error:
            raise PowerMeterError("Unexpected JSON response format") from error

        return PowerMeasurementResult(float(power), time.time())

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
