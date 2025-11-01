from __future__ import annotations

import re
from typing import NamedTuple

from homeassistant.components.light import ATTR_SUPPORTED_COLOR_MODES, ColorMode
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, split_entity_id
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.template import is_number
import voluptuous as vol

from .const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_MULTI_SWITCH,
    CONF_POWER_SENSOR_ID,
    CONF_SENSOR_TYPE,
    DUMMY_ENTITY_ID,
    SensorType,
)
from .errors import SensorConfigurationError


class SourceEntity(NamedTuple):
    object_id: str
    entity_id: str
    domain: str
    unique_id: str | None = None
    name: str | None = None
    supported_color_modes: list[ColorMode] | None = None
    entity_entry: er.RegistryEntry | None = None
    device_entry: dr.DeviceEntry | None = None


async def create_source_entity(entity_id: str, hass: HomeAssistant) -> SourceEntity:
    """Create object containing all information about the source entity."""

    source_entity_domain, source_object_id = split_entity_id(entity_id)
    if entity_id == DUMMY_ENTITY_ID:
        return SourceEntity(
            object_id=source_object_id,
            entity_id=DUMMY_ENTITY_ID,
            domain=source_entity_domain,
        )

    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get(entity_id)

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(entity_entry.device_id) if entity_entry and entity_entry.device_id else None

    unique_id = None
    supported_color_modes: list[ColorMode] = []
    if entity_entry:
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id
        if entity_entry.capabilities:
            supported_color_modes = entity_entry.capabilities.get(  # type: ignore[assignment]
                ATTR_SUPPORTED_COLOR_MODES,
            )

    entity_state = hass.states.get(entity_id)
    if entity_state:
        supported_color_modes = entity_state.attributes.get(ATTR_SUPPORTED_COLOR_MODES)

    return SourceEntity(
        source_object_id,
        entity_id,
        source_entity_domain,
        unique_id,
        get_wrapped_entity_name(
            hass,
            entity_id,
            source_object_id,
            entity_entry,
            device_entry,
        ),
        supported_color_modes or [],
        entity_entry,
        device_entry,
    )


def get_wrapped_entity_name(
    hass: HomeAssistant,
    entity_id: str,
    object_id: str,
    entity_entry: er.RegistryEntry | None,
    device_entry: dr.DeviceEntry | None,
) -> str:
    """Construct entity name based on the wrapped entity"""
    if entity_entry:
        if entity_entry.name:
            return entity_entry.name
        if entity_entry.has_entity_name and device_entry:
            device_name = device_entry.name_by_user or device_entry.name
            if device_name:
                return f"{device_name} {entity_entry.original_name}" if entity_entry.original_name else device_name

        return entity_entry.original_name or object_id

    entity_state = hass.states.get(entity_id)
    if entity_state:
        return str(entity_state.name)

    return object_id


def get_merged_sensor_configuration(*configs: dict, validate: bool = True) -> dict:
    """Merges configuration from multiple levels (global, group, sensor) into a single dict."""
    exclude_from_merging = [
        CONF_NAME,
        CONF_ENTITY_ID,
        CONF_UNIQUE_ID,
        CONF_POWER_SENSOR_ID,
        CONF_FORCE_ENERGY_SENSOR_CREATION,
    ]
    num_configs = len(configs)

    merged_config = {}
    for i, config in enumerate(configs, 1):
        config_copy = config.copy()
        # Remove config properties which are only allowed on the deepest level
        if i < num_configs:
            for key in exclude_from_merging:
                if key in config:
                    config_copy.pop(key)

        merged_config.update(config_copy)

    if CONF_CREATE_ENERGY_SENSOR not in merged_config:
        merged_config[CONF_CREATE_ENERGY_SENSOR] = merged_config.get(
            CONF_CREATE_ENERGY_SENSORS,
        )

    is_entity_id_required = not any(key in merged_config for key in (CONF_DAILY_FIXED_ENERGY, CONF_POWER_SENSOR_ID, CONF_MULTI_SWITCH))

    if not is_entity_id_required and CONF_ENTITY_ID not in merged_config:
        merged_config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID

    sensor_type = merged_config.get(CONF_SENSOR_TYPE)
    if validate and CONF_CREATE_GROUP not in merged_config and CONF_ENTITY_ID not in merged_config and sensor_type != SensorType.GROUP:
        raise SensorConfigurationError(
            "You must supply an entity_id in the configuration, see the README",
        )

    return merged_config


def validate_name_pattern(value: str) -> str:
    """Validate that the naming pattern contains {}."""
    regex = re.compile(r"{}")
    if not regex.search(value):
        raise vol.Invalid("Naming pattern must contain {}")
    return value


def validate_is_number(value: str) -> str:
    """Validate value is a number."""
    if is_number(value):  # type: ignore[no-untyped-call]
        return value
    raise vol.Invalid("Value is not a number")
