from __future__ import annotations

import logging
import time

import requests

from .errors import ConnectionError
from .powermeter import PowerMeasurementResult, PowerMeter

_LOGGER = logging.getLogger("measure")

class ShellyApi:
    status_endpoint = "/status"
    meter_endpoint = "/meter/0"

    def parse_json(self, json: str) -> tuple(float, float):
        pass

class ShellyApiGen1(ShellyApi):
    api_version = 1
    def parse_json(self, json) -> tuple(float, float):
        return (
            float(json["power"]),
            float(json["timestamp"])
        )

class ShellyApiGen2(ShellyApi):
    api_version = 2
    status_endpoint = "/rpc/Shelly.GetStatus"
    meter_endpoint = "/rpc/Switch.GetStatus?id=0"

    def parse_json(self, json) -> tuple(float, float):
        return (
            float(json["apower"]),
            time.time()
        )


class ShellyPowerMeter(PowerMeter):
    def __init__(self, shelly_ip: str, timeout: int = 5):
        self.timeout = timeout
        self.ip_address = shelly_ip
        self.api = self.detect_api_type()

    def get_power(self) -> PowerMeasurementResult:
        try:
            r = requests.get("http://{}{}".format(self.ip_address, self.api.meter_endpoint), timeout=self.timeout)
        except requests.RequestException as e:
            _LOGGER.error("Problem connecting to Shelly plug: %s", e)
            raise ConnectionError("Could not connect to Shelly Plug")

        json = r.json()
        power = self.api.parse_json(json)
        return PowerMeasurementResult(power[0], power[1])

    def detect_api_type(self) -> ShellyApi:
        for api in (ShellyApiGen1(), ShellyApiGen2()):
            return api
            try:
                uri = "http://{}{}".format(self.ip_address, api.status_endpoint)
                _LOGGER.debug(f"Checking API connection: {uri}")
                response = requests.get(uri, timeout=self.timeout)
            except requests.RequestException:
                _LOGGER.error("Connection could not be established")
                continue

            if response.status_code != 200:
                _LOGGER.error(f"Unexpected status code {response.status_code}")
                continue
        
            _LOGGER.debug(f"Shelly API version {api.api_version} detected")
            return api

        raise ConnectionError("Could not connect to Shelly Plug")
