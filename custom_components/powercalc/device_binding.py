from dataclasses import replace
import logging
from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import AnyDeviceEntry, SourceEntity
from custom_components.powercalc.const import CONF_AREA

_LOGGER = logging.getLogger(__name__)

_HAS_SINGLE_CONFIG_ENTRY = hasattr(DeviceEntry, "config_entry_id")
_HAS_CHILD_DEVICES = hasattr(device_registry, "ChildDeviceEntry")


def is_composite_device_id(hass: HomeAssistant, device_id: str) -> bool:
    """Return whether a device ID identifies a legacy composite device."""
    device_reg = device_registry.async_get(hass)
    if _HAS_CHILD_DEVICES:
        return (
            device_reg.async_get(device_id) is not None
            and device_reg.async_get(
                device_id,
                include_composite_devices=False,
            )
            is None
        )

    is_composite = getattr(device_reg, "async_is_composite_device_id", None)
    if not callable(is_composite):
        return False  # pragma: no cover
    return bool(is_composite(device_id))  # pragma: no cover


def get_non_composite_devices(hass: HomeAssistant) -> list[DeviceEntry]:
    """Return all registered devices which are not legacy composite devices.

    Composite devices are synthesized on lookup and are not included in registry enumeration.
    """
    device_reg = device_registry.async_get(hass)
    return (
        list(device_reg.devices)
        if _HAS_CHILD_DEVICES
        else list(cast(dict[str, DeviceEntry], device_reg.devices).values())  # pragma: no cover
    )


def get_related_device_ids(hass: HomeAssistant, device_id: str) -> set[str]:
    """
    Return the IDs of all devices representing the same physical device, including `device_id` itself.
    Devices are related when they were split off from the same legacy composite device, or when they
    share any identifier or connection. Both happen when a single physical device is provided by more
    than one config entry.
    `device_id` may be the ID of a registered device, or of a legacy composite device.
    """
    device_reg = device_registry.async_get(hass)
    related = {device_id}
    related.update(device.id for device in _get_composite_split_devices(device_reg, device_id))

    device = device_reg.async_get(device_id)
    if not isinstance(device, DeviceEntry):
        return related

    sibling_devices = _get_composite_split_devices(device_reg, getattr(device, "composite_device_id", None))
    related.update(sibling_device.id for sibling_device in sibling_devices)

    # Only available in HA >=2026.8. On older versions devices sharing an identifier or connection
    # were merged into a single device, so there is nothing to relate.
    get_devices = getattr(device_reg, "async_get_devices", None)
    if callable(get_devices):
        related.update(
            linked_device.id
            for linked_device in get_devices(identifiers=device.identifiers, connections=device.connections)
        )

    return related


def _get_composite_split_devices(
    device_reg: device_registry.DeviceRegistry,
    composite_device_id: str | None,
) -> list[DeviceEntry]:
    """
    Return the devices a legacy composite device was split into.
    Returns an empty list when the ID does not identify a composite device, or when running on
    HA <2026.8, which does not split composite devices at all.
    """
    if not composite_device_id:
        return []
    get_split_devices = getattr(device_reg, "async_get_devices_for_composite_device_id", None)
    if not callable(get_split_devices):
        return []  # pragma: no cover
    return list(get_split_devices(composite_device_id))


def get_config_entry_ids(device: AnyDeviceEntry) -> set[str]:
    """
    Return the config entry IDs a device belongs to.
    HA >=2026.8 splits composite devices, so a device belongs to exactly one config entry and
    carries a single config_entry_id. Older versions track the set of entries on the device itself.
    """
    if _HAS_SINGLE_CONFIG_ENTRY:
        return {device.config_entry_id}
    return set(getattr(device, "config_entries", set()))  # pragma: no cover


def get_first_device_for_config_entry(hass: HomeAssistant, config_entry_id: str) -> DeviceEntry | None:
    """Return the first non-composite device belonging to a config entry."""
    return next(iter(get_devices_for_config_entry(hass, config_entry_id)), None)


def get_devices_for_config_entry(hass: HomeAssistant, config_entry_id: str) -> list[DeviceEntry]:
    """Return all non-composite devices belonging to a config entry."""
    device_reg = device_registry.async_get(hass)
    return list(device_registry.async_entries_for_config_entry(device_reg, config_entry_id))


def get_related_devices(hass: HomeAssistant, device_id: str) -> list[DeviceEntry]:
    """Return all non-composite devices belonging to the same config entry as the given device."""
    device = device_registry.async_get(hass).async_get(device_id)
    if device is None:
        return []

    devices: dict[str, DeviceEntry] = {}
    for config_entry_id in get_config_entry_ids(device):
        devices.update({related.id: related for related in get_devices_for_config_entry(hass, config_entry_id)})
    return list(devices.values())


def resolve_source_device(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity,
) -> SourceEntity:
    """Attach the configured device entry to a device-based source entity."""
    if not source_entity.is_dummy:
        return source_entity

    device_entry = get_device_entry(hass, sensor_config=sensor_config)
    if device_entry:
        return replace(source_entity, device_entry=device_entry)
    return source_entity


def assign_device_to_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None,
    entities_to_add: list[Entity],
    source_entity: SourceEntity | None,
    sensor_config: ConfigType | None = None,
) -> None:
    """Set entities to the configured or source device, if any available."""

    device_entry = get_device_entry(hass, sensor_config, source_entity, config_entry)
    if not device_entry:
        return

    for entity in entities_to_add:
        # Home Assistant only accepts `device_entry` on entities belonging to a config entry.
        # Setting it for YAML entities makes HA report a deprecation warning, so those rely
        # solely on the registry update `bind_entity_to_device` does after they are added.
        if config_entry:
            entity.device_entry = device_entry
        setattr(entity, "_powercalc_device_entry", device_entry)  # noqa: B010


def get_device_entry(
    hass: HomeAssistant,
    sensor_config: ConfigType | None = None,
    source_entity: SourceEntity | None = None,
    config_entry: ConfigEntry | None = None,
) -> AnyDeviceEntry | None:
    """
    Get device entry for a given powercalc entity configuration.
    Prefer user configured device, when it is not set fallback to the same device as the source entity
    """
    device_id = None
    if sensor_config is not None:
        device_id = sensor_config.get(CONF_DEVICE)
    if device_id is None and config_entry is not None:
        device_id = config_entry.data.get(CONF_DEVICE)
    if device_id is not None:
        if is_composite_device_id(hass, device_id):
            return None
        return device_registry.async_get(hass).async_get(device_id)

    if source_entity and not source_entity.config_entry_id:
        return source_entity.device_entry or async_entity_id_to_device(hass, source_entity.entity_id)

    return None


@callback
def bind_entity_to_registry_metadata(
    hass: HomeAssistant,
    entity_id: str | None,
    device_entry: AnyDeviceEntry | None,
    sensor_config: ConfigType | None,
) -> None:
    """Bind a Powercalc entity to configured registry metadata."""
    if entity_id is None:
        return

    entity_reg = er.async_get(hass)
    entity_entry = entity_reg.async_get(entity_id)
    if entity_entry is None:
        return

    bind_entity_to_device(entity_reg, entity_entry, device_entry)
    bind_entity_to_area(entity_reg, entity_entry, sensor_config.get(CONF_AREA) if sensor_config else None)


@callback
def bind_entity_to_device(
    entity_reg: er.EntityRegistry,
    entity_entry: RegistryEntry,
    device_entry: AnyDeviceEntry | None,
) -> None:
    """Bind a Powercalc entity to the resolved device."""
    # Home Assistant only consumes entity.device_entry while creating registry
    # entries for config-entry platforms. YAML/platform entities need this
    # registry update after they have been added.
    if device_entry is None:
        return

    if entity_entry.config_entry_id is not None or entity_entry.device_id == device_entry.id:
        return

    _LOGGER.debug("Binding %s to device %s", entity_entry.entity_id, device_entry.id)
    entity_reg.async_update_entity(entity_entry.entity_id, device_id=device_entry.id)


@callback
def bind_entity_to_area(
    entity_reg: er.EntityRegistry,
    entity_entry: RegistryEntry,
    area_id: str | None,
) -> None:
    """Bind a Powercalc entity to the configured area."""
    if not area_id:
        return

    if entity_entry.area_id == area_id:
        return

    _LOGGER.debug("Binding %s to area %s", entity_entry.entity_id, area_id)
    entity_reg.async_update_entity(entity_entry.entity_id, area_id=area_id)
