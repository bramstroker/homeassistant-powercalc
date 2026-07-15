from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
import logging
from typing import Any

from homeassistant_api.errors import HomeassistantAPIError
from pydantic import BaseModel, Field
import requests

from measure.const import (
    SHELLY_DISCOVERY_COLLECTION_WINDOW_SECONDS,
    SHELLY_DISCOVERY_MAX_CONCURRENT_PROBES,
    SHELLY_DISCOVERY_PROBE_TIMEOUT_SECONDS,
    ZEROCONF_HTTP_SERVICE_TYPE,
    ZEROCONF_SHELLY_SERVICE_TYPE,
)
from measure.home_assistant import HomeAssistantDiscoveryError, HomeAssistantManager
from measure.powermeter.const import SHELLY_GEN1_STATUS_ENDPOINT, SHELLY_GEN2_STATUS_ENDPOINTS, SHELLY_INFO_ENDPOINT

_LOGGER = logging.getLogger("measure")


class _EndpointProbeResult(StrEnum):
    SUPPORTED = "supported"
    AUTH_REQUIRED = "auth_required"
    UNAVAILABLE = "unavailable"


class ShellyDiscoveredDevice(BaseModel):
    id: str
    name: str
    model: str | None = None
    generation: int | None = None
    ip_address: str
    supported: bool
    reason: str | None = None
    auth_required: bool = False


class ShellyDiscoveryResponse(BaseModel):
    devices: list[ShellyDiscoveredDevice] = Field(default_factory=list)
    available: bool = True
    message: str | None = None


@dataclass(frozen=True)
class _ShellyCandidate:
    name: str
    ip_address: str


class ShellyDiscoveryService:
    """Discover and validate Shelly power meters through Home Assistant."""

    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        *,
        http_get: Callable[..., requests.Response] = requests.get,
    ) -> None:
        self._home_assistant = home_assistant
        self._http_get = http_get

    async def discover(self) -> ShellyDiscoveryResponse:
        try:
            services = await self._home_assistant.discover_zeroconf(SHELLY_DISCOVERY_COLLECTION_WINDOW_SECONDS)
        except (HomeAssistantDiscoveryError, HomeassistantAPIError, OSError, TimeoutError) as error:
            _LOGGER.warning("Shelly discovery through Home Assistant failed: %s", error)
            return ShellyDiscoveryResponse(
                available=False,
                message="Automatic Shelly discovery is unavailable. Enter the IP address manually.",
            )

        candidates = self._candidates(services)
        semaphore = asyncio.Semaphore(SHELLY_DISCOVERY_MAX_CONCURRENT_PROBES)

        async def probe(candidate: _ShellyCandidate) -> ShellyDiscoveredDevice:
            async with semaphore:
                return await asyncio.to_thread(self._probe, candidate)

        devices = await asyncio.gather(*(probe(candidate) for candidate in candidates))
        unique_devices: dict[str, ShellyDiscoveredDevice] = {}
        for device in devices:
            existing = unique_devices.get(device.id)
            if existing is None or (device.supported and not existing.supported):
                unique_devices[device.id] = device
        return ShellyDiscoveryResponse(
            devices=sorted(
                unique_devices.values(),
                key=lambda device: (not device.supported, device.name.casefold()),
            ),
        )

    @staticmethod
    def _candidates(services: tuple[dict[str, object], ...]) -> list[_ShellyCandidate]:
        candidates: dict[str, _ShellyCandidate] = {}
        for service in services:
            service_type = service.get("type")
            name = service.get("name")
            if not isinstance(service_type, str) or not isinstance(name, str):
                continue
            if service_type != ZEROCONF_SHELLY_SERVICE_TYPE and not (
                service_type == ZEROCONF_HTTP_SERVICE_TYPE and name.casefold().startswith("shelly")
            ):
                continue
            addresses = service.get("ip_addresses")
            if not isinstance(addresses, list):
                continue
            strings = [address for address in addresses if isinstance(address, str)]
            if not strings:
                continue
            selected = next(
                (address for address in strings if isinstance(_parse_address(address), IPv4Address)),
                strings[0],
            )
            candidates.setdefault(selected, _ShellyCandidate(name=_service_name(name), ip_address=selected))
        return list(candidates.values())

    def _probe(self, candidate: _ShellyCandidate) -> ShellyDiscoveredDevice:
        address = _parse_address(candidate.ip_address)
        if not isinstance(address, IPv4Address):
            return _unsupported(candidate, "IPv6-only Shelly devices are not supported yet")
        if not _is_safe_lan_address(address):
            return _unsupported(candidate, "The discovered address is not a private LAN address")

        info_result = self._fetch_info(candidate, address)
        if isinstance(info_result, ShellyDiscoveredDevice):
            return info_result
        device = _device_from_info(candidate, info_result)
        if device.auth_required:
            return device
        return self._probe_power_support(address, device)

    def _fetch_info(
        self,
        candidate: _ShellyCandidate,
        address: IPv4Address,
    ) -> dict[str, Any] | ShellyDiscoveredDevice:
        try:
            info_response = self._http_get(
                f"http://{address}{SHELLY_INFO_ENDPOINT}",
                timeout=SHELLY_DISCOVERY_PROBE_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.RequestException:
            return _unsupported(candidate, "The Shelly device could not be reached")
        if info_response.status_code in {401, 403}:
            return _unsupported(candidate, "Authentication is enabled and is not supported yet", auth_required=True)
        if info_response.status_code != 200:
            return _unsupported(candidate, f"The Shelly information endpoint returned HTTP {info_response.status_code}")

        try:
            info = info_response.json()
        except ValueError:
            return _unsupported(candidate, "The Shelly information response was invalid")
        if not isinstance(info, dict):
            return _unsupported(candidate, "The Shelly information response was invalid")
        return info

    def _probe_power_support(self, address: IPv4Address, device: ShellyDiscoveredDevice) -> ShellyDiscoveredDevice:
        endpoints = (SHELLY_GEN1_STATUS_ENDPOINT,) if device.generation == 1 else SHELLY_GEN2_STATUS_ENDPOINTS
        for endpoint in endpoints:
            endpoint_result = self._probe_power_endpoint(address, endpoint)
            if endpoint_result is _EndpointProbeResult.SUPPORTED:
                return device.model_copy(update={"supported": True, "reason": None})
            if endpoint_result is _EndpointProbeResult.AUTH_REQUIRED:
                return device.model_copy(
                    update={"reason": "Authentication is enabled and is not supported yet", "auth_required": True},
                )
        return device.model_copy(update={"reason": "No supported power measurement endpoint was found"})

    def _probe_power_endpoint(self, address: IPv4Address, endpoint: str) -> _EndpointProbeResult:
        try:
            response = self._http_get(
                f"http://{address}{endpoint}",
                timeout=SHELLY_DISCOVERY_PROBE_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.RequestException:
            return _EndpointProbeResult.UNAVAILABLE
        if response.status_code in {401, 403}:
            return _EndpointProbeResult.AUTH_REQUIRED
        if response.status_code != 200:
            return _EndpointProbeResult.UNAVAILABLE
        try:
            data = response.json()
        except ValueError:
            return _EndpointProbeResult.UNAVAILABLE
        if not isinstance(data, dict):
            return _EndpointProbeResult.UNAVAILABLE
        if endpoint == SHELLY_GEN1_STATUS_ENDPOINT:
            meters = data.get("meters")
            supports_power = (
                isinstance(meters, list) and bool(meters) and isinstance(meters[0], dict) and "power" in meters[0]
            )
            return _EndpointProbeResult.SUPPORTED if supports_power else _EndpointProbeResult.UNAVAILABLE
        return _EndpointProbeResult.SUPPORTED if "apower" in data else _EndpointProbeResult.UNAVAILABLE


def _parse_address(value: str) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(value)
    except ValueError:
        return None


def _is_safe_lan_address(address: IPv4Address) -> bool:
    unsafe = address.is_loopback or address.is_multicast or address.is_unspecified or address.is_reserved
    return address.is_private and not unsafe


def _service_name(name: str) -> str:
    return name.split("._", maxsplit=1)[0].rstrip(".")


def _unsupported(candidate: _ShellyCandidate, reason: str, *, auth_required: bool = False) -> ShellyDiscoveredDevice:
    return ShellyDiscoveredDevice(
        id=candidate.name.casefold(),
        name=candidate.name,
        ip_address=candidate.ip_address,
        supported=False,
        reason=reason,
        auth_required=auth_required,
    )


def _device_from_info(candidate: _ShellyCandidate, info: dict[str, Any]) -> ShellyDiscoveredDevice:
    generation_value = info.get("gen", 1)
    try:
        generation = int(generation_value)
    except TypeError, ValueError:
        generation = None
    device_id = str(info.get("id") or info.get("mac") or candidate.name).casefold()
    configured_name = info.get("name")
    name = configured_name if isinstance(configured_name, str) and configured_name else candidate.name
    model_value = info.get("model") or info.get("type")
    model = str(model_value) if model_value else None
    auth_required = info.get("auth_en") is True or info.get("auth") is True
    return ShellyDiscoveredDevice(
        id=device_id,
        name=name,
        model=model,
        generation=generation,
        ip_address=candidate.ip_address,
        supported=False,
        reason="Authentication is enabled and is not supported yet" if auth_required else None,
        auth_required=auth_required,
    )
