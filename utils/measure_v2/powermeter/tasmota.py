import urllib.request
from .powermeter import PowerMeter

class TasmotaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str):
        self._device_ip = device_ip

    def get_power(self) -> float:
        contents = str(urllib.request.urlopen("http://" + self._device_ip + "/?m").read())
        contents = contents.split(" W{e}")[0]
        contents = contents.split("{m}")[-1]
        return float(contents)
