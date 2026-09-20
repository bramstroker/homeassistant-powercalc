"""Conservative connectivity defaults from Home Assistant registry metadata."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
import re


class Connectivity(StrEnum):
    ZIGBEE = "zigbee"
    ZWAVE = "zwave"


@dataclass(frozen=True)
class DeviceConnectivityMetadata:
    integration: str
    identifiers: list[tuple[str, str]]
    connections: list[tuple[str, str]]
    is_child_device: bool


@dataclass(frozen=True)
class ConnectivityRule:
    integration: str
    connectivity: Connectivity
    matches: Callable[[DeviceConnectivityMetadata], bool]


INTEGRATION_CONNECTIVITY = {"zha": Connectivity.ZIGBEE, "zwave_js": Connectivity.ZWAVE}
_IEEE_ADDRESS = r"(?:[0-9a-fA-F]{2}:){7}[0-9a-fA-F]{2}"


def _is_zigbee2mqtt_device(metadata: DeviceConnectivityMetadata) -> bool:
    # Zigbee2MQTT's getDevicePayload uses zigbee2mqtt_<IEEE address> for devices;
    # groups and the bridge use different identifiers. MQTT itself is not evidence.
    # https://github.com/Koenkk/zigbee2mqtt/blob/master/lib/extension/homeassistant.ts
    return any(
        namespace == "mqtt" and re.fullmatch(r"zigbee2mqtt_0x[0-9a-fA-F]{16}", identifier) is not None
        for namespace, identifier in metadata.identifiers
    )


def _is_hue_zigbee_device(metadata: DeviceConnectivityMetadata) -> bool:
    if not metadata.is_child_device:
        return False
    # HA Hue v1 uses the light's IEEE address plus endpoint as its identifier.
    # Hue v2/device.py registers its Zigbee address as a 'mac' connection, even
    # though this is an eight-byte IEEE address, not a six-byte network MAC.
    # https://github.com/home-assistant/core/tree/dev/homeassistant/components/hue
    return any(
        namespace == "hue" and re.fullmatch(rf"{_IEEE_ADDRESS}(?:-[0-9a-fA-F]{{2}})?", identifier) is not None
        for namespace, identifier in metadata.identifiers
    ) or any(
        kind == "mac" and re.fullmatch(_IEEE_ADDRESS, address) is not None for kind, address in metadata.connections
    )


def _has_zigbee_connection(metadata: DeviceConnectivityMetadata) -> bool:
    # HA deconz/entity.py records CONNECTION_ZIGBEE for physical devices.
    return any(
        kind == "zigbee" and re.fullmatch(_IEEE_ADDRESS, address) is not None for kind, address in metadata.connections
    )


CONNECTIVITY_RULES = [
    ConnectivityRule("mqtt", Connectivity.ZIGBEE, _is_zigbee2mqtt_device),
    ConnectivityRule("hue", Connectivity.ZIGBEE, _is_hue_zigbee_device),
    ConnectivityRule("deconz", Connectivity.ZIGBEE, _has_zigbee_connection),
]


def detect_connectivity(integration: str | None, device: Mapping[str, object]) -> Connectivity | None:
    """Return a supported default only when all recognized evidence agrees."""
    if not integration or device.get("entry_type") is not None:
        return None
    identifiers = _read_pairs(device.get("identifiers", []))
    connections = _read_pairs(device.get("connections", []))
    if identifiers is None or connections is None:
        return None
    metadata = DeviceConnectivityMetadata(
        integration=integration,
        identifiers=identifiers,
        connections=connections,
        is_child_device=isinstance(device.get("via_device_id"), str) and bool(device["via_device_id"]),
    )
    candidates: set[Connectivity] = set()
    if connectivity := INTEGRATION_CONNECTIVITY.get(integration):
        candidates.add(connectivity)
    for rule in CONNECTIVITY_RULES:
        if rule.integration == integration and rule.matches(metadata):
            candidates.add(rule.connectivity)
    if len(candidates) != 1:
        return None
    detected = candidates.pop()
    # Explicit evidence of a second protocol is ambiguous, not a reason to guess
    # a multi-connectivity profile. Generic 'mac' connections say nothing about Wi-Fi.
    protocols = {kind for kind, _ in connections if kind in {"zigbee", "zwave", "bluetooth"}}
    if "zwave_js" in {namespace for namespace, _ in identifiers}:
        protocols.add("zwave")
    return detected if protocols <= {detected} else None


def _read_pairs(value: object) -> list[tuple[str, str]] | None:
    if not isinstance(value, list):
        return None
    pairs: list[tuple[str, str]] = []
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return None
        kind, identifier = pair
        if not isinstance(kind, str) or not isinstance(identifier, str) or not kind or not identifier:
            return None
        pairs.append((kind, identifier))
    return pairs
