from __future__ import annotations

import time
import urllib.request

from .powermeter import PowerMeasurementResult, PowerMeter


class TasmotaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str):
        self._device_ip = device_ip

    def get_power(self) -> PowerMeasurementResult:
        contents = str(
            urllib.request.urlopen("http://" + self._device_ip + "/?m").read()
        )
        contents = contents.split(" W{e}")[0]
        contents = contents.split("{m}")[-1]
        return PowerMeasurementResult(float(contents), time.time())
