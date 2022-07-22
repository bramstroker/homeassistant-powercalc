from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import async_generate_entity_id

from ..common import SourceEntity
from ..const import (
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"


def generate_power_sensor_name(
    sensor_config: dict[str, Any],
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for a power sensor"""
    return _generate_sensor_name(
        sensor_config,
        CONF_POWER_SENSOR_NAMING,
        CONF_POWER_SENSOR_FRIENDLY_NAMING,
        name,
        source_entity,
    )


def generate_energy_sensor_name(
    sensor_config: dict[str, Any],
    name: str | None = None,
    source_entity: SourceEntity | None = None,
) -> str:
    """Generates the name to use for an energy sensor"""
    return _generate_sensor_name(
        sensor_config,
        CONF_ENERGY_SENSOR_NAMING,
        CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
        name,
        source_entity,
    )


def _generate_sensor_name(
    sensor_config: dict[str, Any],
    naming_conf_key: str,
    friendly_naming_conf_key: str,
    name: str | None = None,
    source_entity: SourceEntity | None = None,
):
    """Generates the name to use for an sensor"""
    name_pattern: str = sensor_config.get(naming_conf_key)
    if name is None and source_entity:
        name = source_entity.name
    if friendly_naming_conf_key in sensor_config:
        friendly_name_pattern: str = sensor_config.get(friendly_naming_conf_key)
        name = friendly_name_pattern.format(name)
    else:
        name = name_pattern.format(name)
    return name


@callback
def generate_power_sensor_entity_id(
    hass: HomeAssistant,
    sensor_config: dict[str, Any],
    source_entity: SourceEntity | None = None,
    name: str | None = None,
) -> str:
    """Generates the entity_id to use for a power sensor"""
    name_pattern: str = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    object_id = name or sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        ENTITY_ID_FORMAT, name_pattern.format(object_id), hass=hass
    )
    return entity_id


@callback
def generate_energy_sensor_entity_id(
    hass: HomeAssistant,
    sensor_config: dict[str, Any],
    source_entity: SourceEntity | None = None,
    name: str | None = None,
) -> str:
    """Generates the entity_id to use for an energy sensor"""
    name_pattern: str = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    object_id = name or sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        ENTITY_ID_FORMAT, name_pattern.format(object_id), hass=hass
    )
    return entity_id
