from datetime import timedelta
import logging

from homeassistant.components.utility_meter import DEFAULT_OFFSET
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENABLED, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_STANDBY_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISCOVERY,
    CONF_ENABLE_ANALYTICS,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_EXCLUDE_DEVICE_TYPES,
    CONF_EXCLUDE_SELF_USAGE,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_POWER_UPDATE_INTERVAL,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TYPES,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENERGY_UNIT_PREFIX,
    DEFAULT_ENERGY_UPDATE_INTERVAL,
    DEFAULT_ENTITY_CATEGORY,
    DEFAULT_GROUP_ENERGY_UPDATE_INTERVAL,
    DEFAULT_GROUP_POWER_UPDATE_INTERVAL,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_POWER_SENSOR_PRECISION,
    DEFAULT_UTILITY_METER_TYPES,
    DOMAIN,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
)
from custom_components.powercalc.migrate import handle_legacy_discovery_config, handle_legacy_update_interval_config

FLAG_HAS_GLOBAL_GUI_CONFIG = "has_global_gui_config"

_LOGGER = logging.getLogger(__name__)


async def get_global_configuration(hass: HomeAssistant, config: ConfigType) -> ConfigType:
    # Default configuration values
    default_config = {
        CONF_ENABLE_ANALYTICS: False,
        CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
        CONF_POWER_SENSOR_PRECISION: DEFAULT_POWER_SENSOR_PRECISION,
        CONF_POWER_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
        CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
        CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
        CONF_ENERGY_SENSOR_PRECISION: DEFAULT_ENERGY_SENSOR_PRECISION,
        CONF_ENERGY_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
        CONF_ENERGY_SENSOR_UNIT_PREFIX: DEFAULT_ENERGY_UNIT_PREFIX,
        CONF_GROUP_ENERGY_UPDATE_INTERVAL: DEFAULT_GROUP_ENERGY_UPDATE_INTERVAL,
        CONF_GROUP_POWER_UPDATE_INTERVAL: DEFAULT_GROUP_POWER_UPDATE_INTERVAL,
        CONF_ENERGY_UPDATE_INTERVAL: DEFAULT_ENERGY_UPDATE_INTERVAL,
        CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
        CONF_IGNORE_UNAVAILABLE_STATE: False,
        CONF_CREATE_DOMAIN_GROUPS: [],
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_STANDBY_GROUP: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_DISCOVERY: {
            CONF_ENABLED: True,
            CONF_EXCLUDE_SELF_USAGE: False,
            CONF_EXCLUDE_DEVICE_TYPES: [],
        },
        CONF_UTILITY_METER_OFFSET: DEFAULT_OFFSET,
        CONF_UTILITY_METER_TYPES: DEFAULT_UTILITY_METER_TYPES,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
    }

    # First load GUI configuration if available
    global_config = dict(default_config)
    global_config_entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, ENTRY_GLOBAL_CONFIG_UNIQUE_ID)
    if global_config_entry:
        _LOGGER.debug("Found global configuration entry: %s", global_config_entry.data)
        global_config.update(get_global_gui_configuration(global_config_entry))

    # Then override with YAML configuration if available
    yaml_config: dict = config.get(DOMAIN, {})
    if yaml_config:
        global_config.update(yaml_config)

    await handle_legacy_discovery_config(hass, global_config, yaml_config)
    await handle_legacy_update_interval_config(hass, global_config, yaml_config)

    return global_config


def get_global_gui_configuration(config_entry: ConfigEntry) -> ConfigType:
    global_config = dict(config_entry.data)
    if CONF_UTILITY_METER_OFFSET in global_config:
        global_config[CONF_UTILITY_METER_OFFSET] = timedelta(days=global_config[CONF_UTILITY_METER_OFFSET])
    if global_config.get(CONF_ENERGY_SENSOR_CATEGORY):
        global_config[CONF_ENERGY_SENSOR_CATEGORY] = EntityCategory(global_config[CONF_ENERGY_SENSOR_CATEGORY])
    if global_config.get(CONF_POWER_SENSOR_CATEGORY):
        global_config[CONF_POWER_SENSOR_CATEGORY] = EntityCategory(global_config[CONF_POWER_SENSOR_CATEGORY])

    global_config[FLAG_HAS_GLOBAL_GUI_CONFIG] = True

    return global_config
