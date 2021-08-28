import tuyapower

class ShellyPowerMeter(PowerMeter):
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
        (on, w, mA, V, err) = tuyapower.deviceInfo(
            self._device_id,
            self._device_ip,
            self._device_key,
            self._device_version
        )
        
        if(err == "OK"):
            return w
        else:
            return -1
