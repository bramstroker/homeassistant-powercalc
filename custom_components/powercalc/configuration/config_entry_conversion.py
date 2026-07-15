"""Convert config entry data to runtime sensor configuration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.configuration.normalization import normalize_playbooks, normalize_states_power
from custom_components.powercalc.const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CREATE_GROUP,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_LINEAR,
    CONF_ON_TIME,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATES_POWER,
    CONF_UTILITY_METER_OFFSET,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    SensorType,
)


def _convert_template(config: ConfigType, source_key: str, target_key: str, hass: HomeAssistant) -> None:
    if source_key in config:
        config[target_key] = Template(config.pop(source_key), hass)


def convert_config_entry_to_sensor_config(config_entry: ConfigEntry, hass: HomeAssistant) -> ConfigType:
    """Convert the config entry structure to the sensor config used to create the entities."""
    sensor_config = dict(config_entry.data)
    sensor_type = sensor_config.get(CONF_SENSOR_TYPE)
    if sensor_type == SensorType.GROUP:
        sensor_config[CONF_CREATE_GROUP] = sensor_config.get(CONF_NAME)
    elif sensor_type == SensorType.REAL_POWER:
        sensor_config[CONF_POWER_SENSOR_ID] = sensor_config.get(CONF_ENTITY_ID)
        sensor_config[CONF_FORCE_ENERGY_SENSOR_CREATION] = True

    if CONF_DAILY_FIXED_ENERGY in sensor_config:
        daily_fixed_config = dict(sensor_config[CONF_DAILY_FIXED_ENERGY])
        _convert_template(daily_fixed_config, CONF_VALUE_TEMPLATE, CONF_VALUE, hass)
        on_time = daily_fixed_config.get(CONF_ON_TIME)
        daily_fixed_config[CONF_ON_TIME] = (
            timedelta(hours=on_time["hours"], minutes=on_time["minutes"], seconds=on_time["seconds"])
            if on_time
            else timedelta(days=1)
        )
        sensor_config[CONF_DAILY_FIXED_ENERGY] = daily_fixed_config

    if CONF_FIXED in sensor_config:
        fixed_config = dict(sensor_config[CONF_FIXED])
        _convert_template(fixed_config, CONF_POWER_TEMPLATE, CONF_POWER, hass)
        if CONF_STATES_POWER in fixed_config:
            fixed_config[CONF_STATES_POWER] = {
                key: Template(value, hass) if isinstance(value, str) and "{{" in value else value
                for key, value in normalize_states_power(fixed_config[CONF_STATES_POWER]).items()
            }
        sensor_config[CONF_FIXED] = fixed_config

    if CONF_LINEAR in sensor_config:
        sensor_config[CONF_LINEAR] = dict(sensor_config[CONF_LINEAR])

    if CONF_PLAYBOOK in sensor_config:
        playbook_config = dict(sensor_config[CONF_PLAYBOOK])
        playbook_config[CONF_PLAYBOOKS] = normalize_playbooks(playbook_config[CONF_PLAYBOOKS])
        sensor_config[CONF_PLAYBOOK] = playbook_config

    if CONF_CALCULATION_ENABLED_CONDITION in sensor_config:
        sensor_config[CONF_CALCULATION_ENABLED_CONDITION] = Template(
            sensor_config[CONF_CALCULATION_ENABLED_CONDITION],
            hass,
        )

    if CONF_UTILITY_METER_OFFSET in sensor_config:
        sensor_config[CONF_UTILITY_METER_OFFSET] = timedelta(days=sensor_config[CONF_UTILITY_METER_OFFSET])

    return sensor_config
