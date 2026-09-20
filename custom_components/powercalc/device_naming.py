"""Eligibility and relative names for opt-in device naming."""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .common import AnyDeviceEntry, create_source_entity
from .const import (
    CONF_COST_SENSOR_FRIENDLY_NAMING,
    CONF_COST_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FOLLOW_DEVICE_NAME,
    CONF_MODE,
    CONF_MULTI_SWITCH,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_ENERGY_SENSOR_NAMING,
    DEFAULT_COST_NAME_PATTERN,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_STANDBY_ENERGY_NAME_PATTERN,
    DOMAIN,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)
from .device_binding import get_device_entry


@dataclass(frozen=True)
class DeviceName:
    translation_key: str
    placeholders: dict[str, str] | None = None


def get_device_naming_error(hass: HomeAssistant, config: ConfigType, entry: ConfigEntry) -> str | None:
    """Validate the effective configuration without changing existing naming choices."""
    if config.get(CONF_SENSOR_TYPE) != SensorType.VIRTUAL_POWER:
        return "device_naming_unsupported"

    source = create_source_entity(config.get(CONF_ENTITY_ID, DUMMY_ENTITY_ID), hass)
    device = get_device_entry(hass, config, source, entry)
    if device is None or not (device.name_by_user or device.name):
        return "device_naming_no_device"

    if config.get(CONF_MODE) == CalculationStrategy.MULTI_SWITCH or CONF_MULTI_SWITCH in config:
        return "device_naming_ambiguous"

    # A named channel is not the main feature of a device. Do not discard its qualifier.
    if source.entity_entry and source.entity_entry.has_entity_name and source.entity_entry.original_name:
        return "device_naming_ambiguous"

    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry.entry_id or other.data.get(CONF_SENSOR_TYPE) != SensorType.VIRTUAL_POWER:
            continue
        other_source = create_source_entity(other.data.get(CONF_ENTITY_ID, DUMMY_ENTITY_ID), hass)
        other_device = get_device_entry(hass, dict(other.data), other_source, other)
        if other_device and other_device.id == device.id:
            return "device_naming_ambiguous"

    patterns = [
        [CONF_POWER_SENSOR_NAMING, CONF_POWER_SENSOR_FRIENDLY_NAMING, DEFAULT_POWER_NAME_PATTERN],
        [CONF_ENERGY_SENSOR_NAMING, CONF_ENERGY_SENSOR_FRIENDLY_NAMING, DEFAULT_ENERGY_NAME_PATTERN],
        [CONF_COST_SENSOR_NAMING, CONF_COST_SENSOR_FRIENDLY_NAMING, DEFAULT_COST_NAME_PATTERN],
        [CONF_STANDBY_ENERGY_SENSOR_NAMING, CONF_STANDBY_ENERGY_SENSOR_NAMING, DEFAULT_STANDBY_ENERGY_NAME_PATTERN],
    ]
    for naming_key, friendly_key, default in patterns:
        if config.get(friendly_key, config.get(naming_key, default)) != default:
            return "device_naming_custom_pattern"
    return None


def resolve_naming_device(
    hass: HomeAssistant,
    config: ConfigType,
    entry: ConfigEntry | None,
) -> AnyDeviceEntry | None:
    """Fall back to configured names if a previously enabled option cannot be applied."""
    if entry is None or not config.get(CONF_FOLLOW_DEVICE_NAME):
        return None
    if error := get_device_naming_error(hass, config, entry):
        logging.getLogger(__name__).warning(
            "Cannot follow device name for %s: %s; using configured names",
            entry.title,
            error,
        )
        return None
    source = create_source_entity(config.get(CONF_ENTITY_ID, DUMMY_ENTITY_ID), hass)
    return get_device_entry(hass, config, source, entry)
