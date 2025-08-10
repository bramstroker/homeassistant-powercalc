import logging

from awesomeversion import AwesomeVersion
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.const import __version__ as HA_VERSION  # noqa
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceEntry, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.sensors.abstract import BaseEntity

_LOGGER = logging.getLogger(__name__)


async def attach_entities_to_source_device(
    config_entry: ConfigEntry | None,
    entities_to_add: list[Entity],
    hass: HomeAssistant,
    source_entity: SourceEntity | None,
) -> None:
    """Set the entity to same device as the source entity, if any available."""

    device_entry = source_entity.device_entry if source_entity else None
    if not device_entry and config_entry:
        device_id = config_entry.data.get(CONF_DEVICE)
        if device_id:
            device_entry = device_registry.async_get(hass).async_get(device_id)

    if not device_entry:
        return

    if config_entry:
        bind_config_entry_to_device(hass, config_entry, device_entry)

    for entity in (entity for entity in entities_to_add if isinstance(entity, BaseEntity)):
        try:
            if AwesomeVersion(HA_VERSION) >= AwesomeVersion("2025.8.0") and config_entry:
                entity.device_entry = device_entry
            else:
                entity.source_device_id = device_entry.id  # type: ignore
        except AttributeError:  # pragma: no cover
            _LOGGER.error("%s: Cannot set device id on entity", entity.entity_id)


def bind_config_entry_to_device(hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry) -> None:
    """
    When the user selected a specific device in the config flow, bind the config entry to that device
    This will let HA bind all the powercalc entities for that config entry to the concerning device
    """

    if config_entry.entry_id not in device_entry.config_entries:
        device_reg = device_registry.async_get(hass)
        device_reg.async_update_device(
            device_entry.id,
            add_config_entry_id=config_entry.entry_id,
        )

    remove_stale_devices(hass, config_entry, device_entry.id)


def remove_stale_devices(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_id: str,
) -> None:
    """Remove powercalc config entries from old devices."""
    device_reg = device_registry.async_get(hass)
    device_entries = device_registry.async_entries_for_config_entry(
        device_reg,
        config_entry.entry_id,
    )

    stale_devices = [device_entry for device_entry in device_entries if device_entry.id != device_id]

    for device_entry in stale_devices:
        device_reg.async_update_device(
            device_entry.id,
            remove_config_entry_id=config_entry.entry_id,
        )


def get_device_info(hass: HomeAssistant, sensor_config: ConfigType, source_entity: SourceEntity | None) -> DeviceInfo | None:
    """
    Get device info for a given powercalc entity configuration.
    Prefer user configured device, when it is not set fallback to the same device as the source entity
    """
    device_id = sensor_config.get(CONF_DEVICE)
    device = None
    if device_id is not None:
        device_reg = device_registry.async_get(hass)
        device = device_reg.async_get(device_id)
    elif source_entity:
        device = source_entity.device_entry

    if device is None:
        return None

    if not device.identifiers and not device.connections:
        return None

    return DeviceInfo(
        identifiers=device.identifiers,
        connections=device.connections,
    )
