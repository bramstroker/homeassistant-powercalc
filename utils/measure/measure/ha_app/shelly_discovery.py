from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
import logging

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
from measure.powermeter.shelly_client import ShellyClient, ShellyDeviceInfo, ShellyProbeError

_LOGGER = logging.getLogger("measure")


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
        except (HomeAssistantDiscoveryError, HomeassistantAPIError, OSError) as error:
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
    def _candidates(services: Iterable[dict[str, object]]) -> list[_ShellyCandidate]:
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

        client = ShellyClient(str(address), SHELLY_DISCOVERY_PROBE_TIMEOUT_SECONDS, http_get=self._http_get)
        try:
            device = client.probe()
        except ShellyProbeError as error:
            if error.device_info is None:
                return _unsupported(candidate, str(error), auth_required=error.auth_required)
            return _device_from_info(candidate, error.device_info).model_copy(
                update={"reason": str(error), "auth_required": error.auth_required},
            )
        return _device_from_info(candidate, device.info).model_copy(update={"supported": True, "reason": None})


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


def _device_from_info(candidate: _ShellyCandidate, info: ShellyDeviceInfo) -> ShellyDiscoveredDevice:
    return ShellyDiscoveredDevice(
        id=(info.device_id or candidate.name).casefold(),
        name=info.name or candidate.name,
        model=info.model,
        generation=info.generation,
        ip_address=candidate.ip_address,
        supported=False,
        auth_required=info.auth_required,
    )
