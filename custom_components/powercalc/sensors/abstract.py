from __future__ import annotations

import logging

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    DOMAIN,
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


class BaseEntity(Entity):
    async def async_added_to_hass(self) -> None:
        """Attach the entity to same device as the source entity."""
        entity_reg = er.async_get(self.hass)
        entity_entry = entity_reg.async_get(self.entity_id)
        if entity_entry is None or not hasattr(self, "source_device_id"):
            return

        device_id: str = getattr(self, "source_device_id")  # noqa: B009
        device_reg = dr.async_get(self.hass)
        device_entry = device_reg.async_get(device_id)
        if not device_entry or device_entry.id == entity_entry.device_id:  # pragma: no cover
            return
        _LOGGER.debug("Binding %s to device %s", self.entity_id, device_id)
        entity_reg.async_update_entity(self.entity_id, device_id=device_id)


def generate_power_sensor_name(
    sensor_config: ConfigType,
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for a power sensor."""
    return _generate_sensor_name(
        sensor_config,
        CONF_POWER_SENSOR_NAMING,
        CONF_POWER_SENSOR_FRIENDLY_NAMING,
        name,
        source_entity,
    )


def generate_energy_sensor_name(
    sensor_config: ConfigType,
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for an energy sensor."""
    return _generate_sensor_name(
        sensor_config,
        CONF_ENERGY_SENSOR_NAMING,
        CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
        name,
        source_entity,
    )


def _generate_sensor_name(
    sensor_config: ConfigType,
    naming_conf_key: str,
    friendly_naming_conf_key: str,
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for a sensor."""
    if name is None and source_entity:
        name = source_entity.name

    if friendly_naming_conf_key in sensor_config:
        friendly_name_pattern = str(sensor_config.get(friendly_naming_conf_key))
        return friendly_name_pattern.format(name)

    name_pattern = str(sensor_config.get(naming_conf_key))
    return name_pattern.format(name)


@callback
def generate_power_sensor_entity_id(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity | None = None,
    name: str | None = None,
    unique_id: str | None = None,
) -> str:
    """Generates the entity_id to use for a power sensor."""
    if entity_id := get_entity_id_by_unique_id(hass, unique_id):
        return entity_id
    name_pattern = str(sensor_config.get(CONF_POWER_SENSOR_NAMING))
    object_id = name or sensor_config.get(CONF_NAME)
    if object_id is None and source_entity:
        object_id = source_entity.object_id
    return async_generate_entity_id(
        ENTITY_ID_FORMAT,
        name_pattern.format(object_id),
        hass=hass,
    )


@callback
def generate_energy_sensor_entity_id(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity | None = None,
    name: str | None = None,
    unique_id: str | None = None,
) -> str:
    """Generates the entity_id to use for an energy sensor."""
    if entity_id := get_entity_id_by_unique_id(hass, unique_id):
        return entity_id
    name_pattern = str(sensor_config.get(CONF_ENERGY_SENSOR_NAMING))
    object_id = name or sensor_config.get(CONF_NAME)
    if object_id is None and source_entity:
        object_id = source_entity.object_id
    return async_generate_entity_id(
        ENTITY_ID_FORMAT,
        name_pattern.format(object_id),
        hass=hass,
    )


def get_entity_id_by_unique_id(
    hass: HomeAssistant,
    unique_id: str | None,
) -> str | None:
    if unique_id is None:
        return None
    entity_reg = er.async_get(hass)
    return entity_reg.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, unique_id)
