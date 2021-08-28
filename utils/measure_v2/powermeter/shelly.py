import requests
from .powermeter import PowerMeter

class ShellyPowerMeter(PowerMeter):
    def __init__(self, shelly_ip):
        self.meter_uri = "http://{}/meter/{}".format(shelly_ip, 0)

    def get_power(self) -> float:
        r = requests.get(self.meter_uri)
        json = r.json()
        return float(json["power"])
