"""Resolve registry relationships used by portable PowerCalc profile entities."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from measure.home_assistant.const import (
    HASS_DEVICE_REGISTRY_CONFIG_ENTRIES,
    HASS_DEVICE_REGISTRY_CONFIG_ENTRY_ID,
    HASS_DEVICE_REGISTRY_ID,
    HASS_DEVICE_REGISTRY_IDENTIFIERS,
    HASS_DEVICE_REGISTRY_PARENT_DEVICE_ID,
)


@dataclass(frozen=True)
class _Device:
    device_id: str
    parent_id: str | None
    identifiers: set[tuple[str, str]]
    config_entries: set[str]


def map_profile_related_devices(device_registry: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    """Mirror PowerCalc's immediate parent, children, and Roborock dock lookup."""
    devices = []
    for entry in device_registry:
        device_id = _get_device_string(entry, HASS_DEVICE_REGISTRY_ID)
        if device_id is None:
            continue
        devices.append(
            _Device(
                device_id=device_id,
                parent_id=_get_device_string(entry, HASS_DEVICE_REGISTRY_PARENT_DEVICE_ID),
                identifiers=_get_identifiers(entry),
                config_entries=_get_config_entry_ids(entry),
            )
        )
    related = _map_native_children(devices)
    for device in devices:
        for dock_id in _find_roborock_docks(device, devices):
            children = related.setdefault(device.device_id, [])
            if dock_id not in children:
                children.append(dock_id)
    return related


def _map_native_children(devices: Sequence[_Device]) -> dict[str, list[str]]:
    related: dict[str, list[str]] = {}
    known_ids = {device.device_id for device in devices}
    for device in devices:
        if device.parent_id is not None and device.parent_id != device.device_id and device.parent_id in known_ids:
            related.setdefault(device.parent_id, []).append(device.device_id)
            related.setdefault(device.device_id, []).append(device.parent_id)
    return related


def _find_roborock_docks(device: _Device, devices: Sequence[_Device]) -> list[str]:
    dock_identifiers = {
        ("roborock", f"{identifier}_dock") for domain, identifier in device.identifiers if domain == "roborock"
    }
    if not dock_identifiers:
        return []
    return [
        candidate.device_id
        for candidate in devices
        if candidate.device_id != device.device_id
        and candidate.identifiers & dock_identifiers
        and candidate.config_entries & device.config_entries
    ]


def _get_device_string(device: Mapping[str, object], key: str) -> str | None:
    value = device.get(key)
    return value if isinstance(value, str) and value else None


def _get_identifiers(device: Mapping[str, object]) -> set[tuple[str, str]]:
    items = device.get(HASS_DEVICE_REGISTRY_IDENTIFIERS)
    identifiers: set[tuple[str, str]] = set()
    for item in items if isinstance(items, list) else []:
        if isinstance(item, list | tuple) and len(item) == 2 and all(isinstance(part, str) for part in item):
            identifiers.add((item[0], item[1]))
    return identifiers


def _get_config_entry_ids(device: Mapping[str, object]) -> set[str]:
    """Home Assistant 2026.8+ reports one config_entry_id; older versions a config_entries list."""

    entries = device.get(HASS_DEVICE_REGISTRY_CONFIG_ENTRIES)
    entry_ids = {entry for entry in entries if isinstance(entry, str)} if isinstance(entries, list) else set()
    if (entry_id := _get_device_string(device, HASS_DEVICE_REGISTRY_CONFIG_ENTRY_ID)) is not None:
        entry_ids.add(entry_id)
    return entry_ids
