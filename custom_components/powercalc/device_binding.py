import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity

_LOGGER = logging.getLogger(__name__)


async def attach_entities_to_source_device(
    config_entry: ConfigEntry | None,
    entities_to_add: list[Entity],
    hass: HomeAssistant,
    source_entity: SourceEntity | None,
) -> None:
    """Set the entity to same device as the source entity, if any available."""

    device_entry = None
    if source_entity:
        device_entry = async_entity_id_to_device(hass, source_entity.entity_id) or source_entity.device_entry

    if not device_entry and config_entry:
        device_id = config_entry.data.get(CONF_DEVICE)
        if device_id:
            device_entry = device_registry.async_get(hass).async_get(device_id)

    if config_entry:
        remove_config_entry_from_devices(hass, config_entry)

    if not device_entry:
        return

    for entity in entities_to_add:
        try:
            entity.device_entry = device_entry
        except AttributeError:  # pragma: no cover
            _LOGGER.error("%s: Cannot set device id on entity", entity.entity_id)


def remove_config_entry_from_devices(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """
    Remove powercalc config entry from all devices.
    See: https://developers.home-assistant.io/blog/2025/07/18/updated-pattern-for-helpers-linking-to-devices/
    """
    device_reg = device_registry.async_get(hass)
    device_entries = device_registry.async_entries_for_config_entry(
        device_reg,
        config_entry.entry_id,
    )

    for device_entry in device_entries:
        device_reg.async_update_device(
            device_entry.id,
            remove_config_entry_id=config_entry.entry_id,
        )


def get_device_info(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity | None,
) -> DeviceInfo | None:
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
