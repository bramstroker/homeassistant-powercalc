from __future__ import annotations

from .errors import PowerMeterError
from .powermeter import PowerMeter, PowerMeasurementResult
import time
import tuyapower

class TuyaPowerMeter(PowerMeter):
    def __init__(
        self,
        device_id: str,
        device_ip: str,
        device_key: str,
        device_version: str = "3.3"
    ):
        self._device_id = device_id
        self._device_ip = device_ip
        self._device_key = device_key
        self._device_version = device_version

    def get_power(self) -> float:
        #@todo we can get updated at from deviceJson
        (on, w, mA, V, err) = tuyapower.deviceInfo(
            self._device_id,
            self._device_ip,
            self._device_key,
            self._device_version
        )

        if(err != "OK"):
            raise PowerMeterError("Could not get a succesfull power reading")
        
        return PowerMeasurementResult(w, time.time())
        