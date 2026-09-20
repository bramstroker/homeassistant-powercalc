"""Eligibility and relative names for opt-in device naming."""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .common import AnyDeviceEntry, SourceEntity
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
    DOMAIN_CONFIG,
    CalculationStrategy,
    SensorType,
)
from .device_binding import get_device_entry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceName:
    translation_key: str
    placeholders: dict[str, str] | None = None


def get_device_naming_error(
    hass: HomeAssistant,
    config: ConfigType,
    entry: ConfigEntry,
    source: SourceEntity,
    device: AnyDeviceEntry | None,
) -> str | None:
    """Validate the effective configuration without changing existing naming choices."""
    if config.get(CONF_SENSOR_TYPE) != SensorType.VIRTUAL_POWER:
        return "device_naming_unsupported"

    if device is None or not (device.name_by_user or device.name):
        return "device_naming_no_device"

    if config.get(CONF_MODE) == CalculationStrategy.MULTI_SWITCH or CONF_MULTI_SWITCH in config:
        return "device_naming_ambiguous"

    # A named channel is not the main feature of a device. Do not discard its qualifier.
    if source.entity_entry and source.entity_entry.has_entity_name and source.entity_entry.original_name:
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
    if has_other_virtual_power_entry(hass, entry, device.id):
        return "device_naming_ambiguous"
    return None


def has_other_virtual_power_entry(hass: HomeAssistant, entry: ConfigEntry, device_id: str) -> bool:
    """Check whether another virtual power entry is assigned to the device."""
    source_entity_ids = {entity.entity_id for entity in er.async_entries_for_device(er.async_get(hass), device_id)}
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry.entry_id or other.data.get(CONF_SENSOR_TYPE) != SensorType.VIRTUAL_POWER:
            continue
        configured_device_id = other.data.get(CONF_DEVICE)
        if configured_device_id == device_id:
            return True
        if configured_device_id is None and other.data.get(CONF_ENTITY_ID) in source_entity_ids:
            return True
    return False


def should_follow_device_name(
    hass: HomeAssistant,
    config: ConfigType,
    entry: ConfigEntry | None,
    source: SourceEntity,
) -> bool:
    """Use the global naming option, retaining configured names for unsupported entries."""
    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]
    if entry is None or not global_config.get(CONF_FOLLOW_DEVICE_NAME):
        return False
    device = get_device_entry(hass, config, source, entry)
    if error := get_device_naming_error(hass, config, entry, source, device):
        configured_device_missing = (
            error == "device_naming_no_device" and config.get(CONF_DEVICE) is not None and device is None
        )
        log = _LOGGER.warning if configured_device_missing else _LOGGER.debug
        log("Cannot follow device name for %s: %s; using configured names", entry.title, error)
        return False
    return True
