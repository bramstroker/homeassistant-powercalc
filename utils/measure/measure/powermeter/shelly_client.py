from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import math
import time
from typing import Any, TypeGuard

import requests

from measure.powermeter.const import (
    SHELLY_GEN1_STATUS_ENDPOINT,
    SHELLY_INFO_ENDPOINT,
    SHELLY_RPC_DEVICE_STATUS_ENDPOINT,
    SHELLY_RPC_PM1_STATUS_ENDPOINT,
    SHELLY_RPC_SWITCH_STATUS_ENDPOINT,
)
from measure.powermeter.powermeter import PowerMeasurementResult


class ShellyProbeFailure(StrEnum):
    UNREACHABLE = "unreachable"
    AUTH_REQUIRED = "auth_required"
    HTTP_ERROR = "http_error"
    INVALID_RESPONSE = "invalid_response"
    NO_POWER_COMPONENT = "no_power_component"
    MULTIPLE_POWER_COMPONENTS = "multiple_power_components"


class ShellyPowerComponentType(StrEnum):
    GEN1_METER = "meter"
    SWITCH = "switch"
    PM1 = "pm1"


@dataclass(frozen=True)
class ShellyDeviceInfo:
    generation: int
    device_id: str | None
    name: str | None
    model: str | None
    auth_required: bool


@dataclass(frozen=True)
class ShellyPowerComponent:
    type: ShellyPowerComponentType
    id: int
    supports_voltage: bool

    @property
    def status_endpoint(self) -> str:
        if self.type is ShellyPowerComponentType.GEN1_METER:
            return SHELLY_GEN1_STATUS_ENDPOINT
        endpoint = (
            SHELLY_RPC_SWITCH_STATUS_ENDPOINT
            if self.type is ShellyPowerComponentType.SWITCH
            else SHELLY_RPC_PM1_STATUS_ENDPOINT
        )
        return endpoint.format(component_id=self.id)


@dataclass(frozen=True)
class ShellyDevice:
    info: ShellyDeviceInfo
    power_component: ShellyPowerComponent


class ShellyProbeError(Exception):
    def __init__(
        self,
        failure: ShellyProbeFailure,
        message: str,
        *,
        device_info: ShellyDeviceInfo | None = None,
    ) -> None:
        super().__init__(message)
        self.failure = failure
        self.device_info = device_info

    @property
    def auth_required(self) -> bool:
        return self.failure is ShellyProbeFailure.AUTH_REQUIRED


class ShellyClient:
    """Probe and read Shelly Gen1 and Gen2+ power components."""

    def __init__(
        self,
        ip_address: str,
        timeout: int,
        *,
        http_get: Callable[..., requests.Response] | None = None,
    ) -> None:
        self._base_url = f"http://{ip_address}"
        self._timeout = timeout
        self._http_get = http_get or requests.get

    def probe(self) -> ShellyDevice:
        info = self._get_device_info()
        if info.auth_required:
            raise ShellyProbeError(
                ShellyProbeFailure.AUTH_REQUIRED,
                "Authentication is enabled and is not supported yet",
                device_info=info,
            )

        try:
            component = self._probe_gen1() if info.generation == 1 else self._probe_rpc()
        except ShellyProbeError as error:
            raise ShellyProbeError(error.failure, str(error), device_info=info) from error
        return ShellyDevice(info=info, power_component=component)

    def read(self, component: ShellyPowerComponent, *, include_voltage: bool) -> PowerMeasurementResult:
        data = self._request_json(component.status_endpoint, "power measurement")
        if component.type is ShellyPowerComponentType.GEN1_METER:
            return self._parse_gen1_reading(data)
        return self._parse_rpc_reading(data, include_voltage=include_voltage)

    def _get_device_info(self) -> ShellyDeviceInfo:
        data = self._request_json(SHELLY_INFO_ENDPOINT, "information")
        if not isinstance(data, dict):
            raise self._invalid_response("The Shelly information response was invalid")

        generation_value = data.get("gen", 1)
        if isinstance(generation_value, bool):
            raise self._invalid_response("The Shelly generation was invalid")
        try:
            generation = int(generation_value)
        except (TypeError, ValueError) as error:
            raise self._invalid_response("The Shelly generation was invalid") from error
        if generation < 1:
            raise self._invalid_response("The Shelly generation was invalid")

        return ShellyDeviceInfo(
            generation=generation,
            device_id=_optional_string(data.get("id") or data.get("mac")),
            name=_optional_string(data.get("name")),
            model=_optional_string(data.get("model") or data.get("type")),
            auth_required=data.get("auth_en") is True or data.get("auth") is True,
        )

    def _probe_gen1(self) -> ShellyPowerComponent:
        data = self._request_json(SHELLY_GEN1_STATUS_ENDPOINT, "power status")
        self._gen1_meter(data)
        return ShellyPowerComponent(type=ShellyPowerComponentType.GEN1_METER, id=0, supports_voltage=False)

    def _probe_rpc(self) -> ShellyPowerComponent:
        data = self._request_json(SHELLY_RPC_DEVICE_STATUS_ENDPOINT, "RPC status")
        if not isinstance(data, dict):
            raise self._invalid_response("The Shelly RPC status response was invalid")

        components: list[ShellyPowerComponent] = []
        for key, value in data.items():
            component = _power_component(key, value)
            if component is not None:
                components.append(component)

        if not components:
            raise ShellyProbeError(
                ShellyProbeFailure.NO_POWER_COMPONENT,
                "No supported power measurement component was found",
            )
        if len(components) > 1:
            raise ShellyProbeError(
                ShellyProbeFailure.MULTIPLE_POWER_COMPONENTS,
                "Multiple power measurement components were found; multi-channel devices are not supported yet",
            )
        return components[0]

    def _request_json(self, endpoint: str, description: str) -> object:
        try:
            response = self._http_get(
                f"{self._base_url}{endpoint}",
                timeout=self._timeout,
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise ShellyProbeError(
                ShellyProbeFailure.UNREACHABLE,
                "The Shelly device could not be reached",
            ) from error

        if response.status_code in {401, 403}:
            raise ShellyProbeError(
                ShellyProbeFailure.AUTH_REQUIRED,
                "Authentication is enabled and is not supported yet",
            )
        if response.status_code != 200:
            raise ShellyProbeError(
                ShellyProbeFailure.HTTP_ERROR,
                f"The Shelly {description} endpoint returned HTTP {response.status_code}",
            )
        try:
            return response.json()
        except ValueError as error:
            raise self._invalid_response(f"The Shelly {description} response was invalid") from error

    def _parse_gen1_reading(self, data: object) -> PowerMeasurementResult:
        meter = self._gen1_meter(data)
        timestamp = meter.get("timestamp")
        if not _is_number(timestamp):
            raise self._invalid_response("The Shelly Gen1 power status response did not contain a valid timestamp")
        return PowerMeasurementResult(power=float(meter["power"]), updated=float(timestamp))

    def _parse_rpc_reading(self, data: object, *, include_voltage: bool) -> PowerMeasurementResult:
        if not isinstance(data, dict) or not _is_number(data.get("apower")):
            raise self._invalid_response("The Shelly RPC power status response did not contain a valid power value")
        voltage = data.get("voltage")
        voltage_value: float | None = None
        if include_voltage:
            if not _is_number(voltage):
                raise self._invalid_response(
                    "The Shelly RPC power status response did not contain a valid voltage value",
                )
            voltage_value = float(voltage)
        return PowerMeasurementResult(
            power=float(data["apower"]),
            voltage=voltage_value,
            updated=time.time(),
        )

    def _gen1_meter(self, data: object) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise self._invalid_response("The Shelly Gen1 power status response was invalid")
        meters = data.get("meters")
        valid_meter = (
            isinstance(meters, list)
            and bool(meters)
            and isinstance(meters[0], dict)
            and _is_number(meters[0].get("power"))
        )
        if not valid_meter:
            raise self._invalid_response("The Shelly Gen1 power status response did not contain a valid power value")
        assert isinstance(meters, list)
        assert isinstance(meters[0], dict)
        return meters[0]

    @staticmethod
    def _invalid_response(message: str) -> ShellyProbeError:
        return ShellyProbeError(ShellyProbeFailure.INVALID_RESPONSE, message)


def _power_component(key: object, value: object) -> ShellyPowerComponent | None:
    if not isinstance(key, str) or not isinstance(value, dict) or not _is_number(value.get("apower")):
        return None
    type_value, separator, component_id_value = key.partition(":")
    if not separator or not component_id_value.isdecimal():
        return None
    try:
        component_type = ShellyPowerComponentType(type_value)
    except ValueError:
        return None
    if component_type is ShellyPowerComponentType.GEN1_METER:
        return None
    return ShellyPowerComponent(
        type=component_type,
        id=int(component_id_value),
        supports_voltage=_is_number(value.get("voltage")),
    )


def _is_number(value: object) -> TypeGuard[int | float]:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
