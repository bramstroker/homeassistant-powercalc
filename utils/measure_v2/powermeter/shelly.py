from __future__ import annotations

import datetime

import requests

from .powermeter import PowerMeasurementResult, PowerMeter


class ShellyPowerMeter(PowerMeter):
    def __init__(self, shelly_ip):
        self.meter_uri = "http://{}/meter/{}".format(shelly_ip, 0)

    def get_power(self) -> PowerMeasurementResult:
        r = requests.get(self.meter_uri)
        json = r.json()
        return PowerMeasurementResult(
            float(json["power"]),
            float(json["timestamp"]),
        )
