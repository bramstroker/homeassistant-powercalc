from __future__ import annotations

import logging

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity import Entity, async_generate_entity_id
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_AREA,
    CONF_COST_SENSOR_FRIENDLY_NAMING,
    CONF_COST_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    DEFAULT_COST_NAME_PATTERN,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_POWER_NAME_PATTERN,
    DOMAIN,
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


class BaseEntity(Entity):
    async def async_added_to_hass(self) -> None:
        """Bind configured registry metadata."""

        bind_entity_to_device(self.hass, self.entity_id, self.device_entry)

        if not hasattr(self, "_sensor_config"):
            return

        sensor_config = getattr(self, "_sensor_config")  # noqa: B009
        bind_entity_to_area(self.hass, self.entity_id, sensor_config)


@callback
def bind_entity_to_device(
    hass: HomeAssistant,
    entity_id: str | None,
    device_entry: DeviceEntry | None,
) -> None:
    """Bind a Powercalc entity to the resolved device."""
    # Home Assistant only consumes entity.device_entry while creating registry
    # entries for config-entry platforms. Only YAML/platform entities need this
    # explicit registry update after they have been added.
    if entity_id is None or device_entry is None:
        return

    entity_reg = er.async_get(hass)
    entity_entry = entity_reg.async_get(entity_id)
    if entity_entry is None or entity_entry.config_entry_id is not None or entity_entry.device_id == device_entry.id:
        return

    _LOGGER.debug("Binding %s to device %s", entity_id, device_entry.id)
    entity_reg.async_update_entity(entity_id, device_id=device_entry.id)


@callback
def bind_entity_to_area(
    hass: HomeAssistant,
    entity_id: str | None,
    sensor_config: ConfigType,
) -> None:
    """Bind a Powercalc entity to the configured area."""
    if entity_id is None:
        return

    area_id = sensor_config.get(CONF_AREA)
    if not area_id:
        return

    entity_reg = er.async_get(hass)
    entity_entry = entity_reg.async_get(entity_id)
    if entity_entry is None or entity_entry.area_id == area_id:
        return

    _LOGGER.debug("Binding %s to area %s", entity_id, area_id)
    entity_reg.async_update_entity(entity_id, area_id=area_id)


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
        DEFAULT_POWER_NAME_PATTERN,
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
        DEFAULT_ENERGY_NAME_PATTERN,
        name,
        source_entity,
    )


def generate_cost_sensor_name(
    sensor_config: ConfigType,
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for a cost sensor."""
    return _generate_sensor_name(
        sensor_config,
        CONF_COST_SENSOR_NAMING,
        CONF_COST_SENSOR_FRIENDLY_NAMING,
        DEFAULT_COST_NAME_PATTERN,
        name,
        source_entity,
    )


def _generate_sensor_name(
    sensor_config: ConfigType,
    naming_conf_key: str,
    friendly_naming_conf_key: str,
    default_pattern: str,
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for a sensor."""
    if name is None and source_entity:
        name = source_entity.name

    if friendly_naming_conf_key in sensor_config:
        friendly_name_pattern = str(sensor_config.get(friendly_naming_conf_key))
        return friendly_name_pattern.format(name)

    name_pattern = str(sensor_config.get(naming_conf_key, default_pattern))
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
    name_pattern = str(sensor_config.get(CONF_POWER_SENSOR_NAMING, DEFAULT_POWER_NAME_PATTERN))
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
    name_pattern = str(sensor_config.get(CONF_ENERGY_SENSOR_NAMING, DEFAULT_ENERGY_NAME_PATTERN))
    object_id = name or sensor_config.get(CONF_NAME)
    if object_id is None and source_entity:
        object_id = source_entity.object_id
    return async_generate_entity_id(
        ENTITY_ID_FORMAT,
        name_pattern.format(object_id),
        hass=hass,
    )


@callback
def generate_cost_sensor_entity_id(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity | None = None,
    name: str | None = None,
    unique_id: str | None = None,
) -> str:
    """Generates the entity_id to use for a cost sensor."""
    if entity_id := get_entity_id_by_unique_id(hass, unique_id):
        return entity_id
    name_pattern = str(sensor_config.get(CONF_COST_SENSOR_NAMING, DEFAULT_COST_NAME_PATTERN))
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
