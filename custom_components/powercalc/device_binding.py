import logging

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

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_AREA, DUMMY_ENTITY_ID

_LOGGER = logging.getLogger(__name__)


def is_composite_device_id(hass: HomeAssistant, device_id: str) -> bool:
    """
    Return whether a device ID identifies a legacy composite device.
    Check for availability of async_is_composite_device_id, because this function is only available in HA >=2026.8
    """
    device_reg = device_registry.async_get(hass)
    is_composite = getattr(device_reg, "async_is_composite_device_id", None)
    if not callable(is_composite):
        return False
    return bool(is_composite(device_id))


def attach_configured_device_entry(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity,
) -> SourceEntity:
    """Attach the configured device entry to a device-based source entity."""
    if source_entity.entity_id != DUMMY_ENTITY_ID:
        return source_entity

    device_entry = get_device_entry(hass, sensor_config=sensor_config)
    if device_entry:
        return source_entity._replace(device_entry=device_entry)
    return source_entity


async def attach_entities_to_resolved_device(
    config_entry: ConfigEntry | None,
    entities_to_add: list[Entity],
    hass: HomeAssistant,
    source_entity: SourceEntity | None,
    sensor_config: ConfigType | None = None,
) -> None:
    """Set entities to the configured or source device, if any available."""

    device_entry = get_device_entry(hass, sensor_config, source_entity, config_entry)
    if not device_entry:
        return

    for entity in entities_to_add:
        try:
            entity.device_entry = device_entry
        except AttributeError:  # pragma: no cover
            _LOGGER.error("%s: Cannot set device id on entity", entity.entity_id)


def get_device_entry(
    hass: HomeAssistant,
    sensor_config: ConfigType | None = None,
    source_entity: SourceEntity | None = None,
    config_entry: ConfigEntry | None = None,
) -> DeviceEntry | None:
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

    if source_entity:
        return source_entity.device_entry or async_entity_id_to_device(hass, source_entity.entity_id)

    return None


@callback
def bind_entity_to_registry_metadata(
    hass: HomeAssistant,
    entity_id: str | None,
    device_entry: DeviceEntry | None,
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
    device_entry: DeviceEntry | None,
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
