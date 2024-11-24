from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from measure.powermeter.errors import ApiConnectionError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter

_LOGGER = logging.getLogger("measure")


class ShellyApi(ABC):
    @property
    @abstractmethod
    def endpoint(self) -> str: ...

    @abstractmethod
    def parse_json(self, json: dict) -> PowerMeasurementResult: ...


class ShellyApiGen1(ShellyApi):
    @property
    def endpoint(self) -> str:
        return "/status"

    def parse_json(self, json: dict) -> PowerMeasurementResult:
        meter = json["meters"][0]
        return PowerMeasurementResult(float(meter["power"]), float(meter["timestamp"]))


class ShellyApiGen2(ShellyApi):
    @property
    def endpoint(self) -> str:
        return "/rpc/Switch.GetStatus?id=0"

    def parse_json(self, json: dict) -> PowerMeasurementResult:
        return PowerMeasurementResult(float(json["apower"]), time.time())


class ShellyPowerMeter(PowerMeter):
    def __init__(self, shelly_ip: str, timeout: int = 5) -> None:
        self.timeout = timeout
        self.ip_address = shelly_ip
        api_version = self.detect_api_version()
        self.api = ShellyApiGen1() if api_version == 1 else ShellyApiGen2()

    def get_power(self) -> PowerMeasurementResult:
        """Get a new power reading from the Shelly device"""
        try:
            r = requests.get(
                f"http://{self.ip_address}{self.api.endpoint}",
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            _LOGGER.error("Problem connecting to Shelly plug: %s", e)
            raise ApiConnectionError("Could not connect to Shelly Plug") from e

        json = r.json()
        return self.api.parse_json(json)

    def detect_api_version(self) -> int:
        """Check the generation / supported API version. All shelly's should implement the /shelly endpoint"""
        try:
            uri = f"http://{self.ip_address}/shelly"
            _LOGGER.debug("Checking API connection: %s", uri)
            response = requests.get(uri, timeout=self.timeout)
        except requests.RequestException as ex:
            raise ApiConnectionError("Could not connect to Shelly Plug") from ex

        if response.status_code != 200:
            raise ApiConnectionError(
                "Could not connect to Shelly Plug, invalid statusCode",
            )

        json = response.json()
        gen = json.get("gen", 1)
        _LOGGER.debug("Shelly API version %d detected", gen)
        return int(gen)

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
