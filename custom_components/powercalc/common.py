from __future__ import annotations

import math
import re
from typing import NamedTuple

from homeassistant.components.light import ATTR_SUPPORTED_COLOR_MODES, ColorMode
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, split_entity_id
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
import voluptuous as vol

from .const import (
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_COST_SENSORS,
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


EXCLUDE_FROM_PARENT_CONFIG = (
    CONF_NAME,
    CONF_ENTITY_ID,
    CONF_UNIQUE_ID,
    CONF_POWER_SENSOR_ID,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
)
ENTITY_ID_OPTIONAL_KEYS = (CONF_DAILY_FIXED_ENERGY, CONF_POWER_SENSOR_ID, CONF_MULTI_SWITCH)


def is_number(value: str) -> bool:
    """Return whether the value can be converted to a finite float."""
    try:
        fvalue = float(value)
    except TypeError, ValueError:
        return False
    return math.isfinite(fvalue)


def create_source_entity(entity_id: str, hass: HomeAssistant) -> SourceEntity:
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
    device_entry = (
        device_registry.async_get(entity_entry.device_id) if entity_entry and entity_entry.device_id else None
    )

    unique_id = None
    supported_color_modes: list[ColorMode] = []
    if entity_entry:
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id
        if entity_entry.capabilities:
            supported_color_modes = entity_entry.capabilities.get(
                ATTR_SUPPORTED_COLOR_MODES,
                [],
            )

    entity_state = hass.states.get(entity_id)
    if entity_state:
        supported_color_modes = entity_state.attributes.get(ATTR_SUPPORTED_COLOR_MODES, [])

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
    if entity_entry is None:
        return _get_state_name(hass, entity_id) or object_id

    if entity_entry.name:
        return entity_entry.name

    device_entity_name = _get_device_entity_name(entity_entry, device_entry)
    if device_entity_name:
        return device_entity_name

    return entity_entry.original_name or object_id


def _get_device_entity_name(
    entity_entry: er.RegistryEntry,
    device_entry: dr.DeviceEntry | None,
) -> str | None:
    if not entity_entry.has_entity_name or device_entry is None:
        return None

    device_name = device_entry.name_by_user or device_entry.name
    if not device_name:
        return None

    if entity_entry.original_name:
        return f"{device_name} {entity_entry.original_name}"

    return device_name


def _get_state_name(hass: HomeAssistant, entity_id: str) -> str | None:
    entity_state = hass.states.get(entity_id)
    return str(entity_state.name) if entity_state else None


def get_merged_sensor_configuration(*configs: dict, validate: bool = True) -> dict:
    """Merges configuration from multiple levels (global, group, sensor) into a single dict."""
    merged_config = _merge_config_levels(configs)
    _apply_sensor_creation_defaults(merged_config)
    _apply_dummy_entity_id_default(merged_config)
    _validate_entity_id_config(merged_config, validate)

    return merged_config


def _merge_config_levels(configs: tuple[dict, ...]) -> dict:
    """Merge config levels while keeping deepest-level-only fields local."""
    num_configs = len(configs)

    merged_config = {}
    for i, config in enumerate(configs, 1):
        config_copy = config.copy()
        if i < num_configs:
            for key in EXCLUDE_FROM_PARENT_CONFIG:
                config_copy.pop(key, None)

        merged_config.update(config_copy)
    return merged_config


def _apply_sensor_creation_defaults(config: dict) -> None:
    config.setdefault(CONF_CREATE_ENERGY_SENSOR, config.get(CONF_CREATE_ENERGY_SENSORS))
    config.setdefault(CONF_CREATE_COST_SENSOR, config.get(CONF_CREATE_COST_SENSORS))


def _apply_dummy_entity_id_default(config: dict) -> None:
    if not _is_entity_id_required(config) and CONF_ENTITY_ID not in config:
        config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID


def _is_entity_id_required(config: dict) -> bool:
    return not any(key in config for key in ENTITY_ID_OPTIONAL_KEYS)


def _validate_entity_id_config(config: dict, validate: bool) -> None:
    if _is_missing_required_entity_id(config, validate):
        raise SensorConfigurationError(
            "You must supply an entity_id in the configuration, see the README",
        )


def _is_missing_required_entity_id(config: dict, validate: bool) -> bool:
    sensor_type = config.get(CONF_SENSOR_TYPE)
    return (
        validate
        and CONF_CREATE_GROUP not in config
        and CONF_ENTITY_ID not in config
        and sensor_type != SensorType.GROUP
    )


def validate_name_pattern(value: str) -> str:
    """Validate that the naming pattern contains {}."""
    regex = re.compile(r"{}")
    if not regex.search(value):
        raise vol.Invalid("Naming pattern must contain {}")
    return value


def validate_is_number(value: str) -> str:
    """Validate value is a number."""
    if is_number(value):
        return value
    raise vol.Invalid("Value is not a number")
