"""Convert config entry data to runtime sensor configuration."""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any

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


def convert_config_entry_to_sensor_config(config_entry: ConfigEntry, hass: HomeAssistant) -> ConfigType:  # noqa: C901
    """Convert the config entry structure to the sensor config used to create the entities."""
    sensor_config = dict(config_entry.data.copy())
    sensor_type = sensor_config.get(CONF_SENSOR_TYPE)

    def handle_sensor_type() -> None:
        """Handle sensor type-specific configuration."""
        if sensor_type == SensorType.GROUP:
            sensor_config[CONF_CREATE_GROUP] = sensor_config.get(CONF_NAME)
        elif sensor_type == SensorType.REAL_POWER:
            sensor_config[CONF_POWER_SENSOR_ID] = sensor_config.get(CONF_ENTITY_ID)
            sensor_config[CONF_FORCE_ENERGY_SENSOR_CREATION] = True

    def process_template(config: dict[str, Any], template_key: str, target_key: str) -> None:
        """Convert a template key in the config to a Template object."""
        if template_key in config:
            config[target_key] = Template(config[template_key], hass)
            del config[template_key]

    def process_on_time(config: dict[str, Any]) -> None:
        """Convert on_time dictionary to timedelta."""
        on_time = config.get(CONF_ON_TIME)
        config[CONF_ON_TIME] = (
            timedelta(hours=on_time["hours"], minutes=on_time["minutes"], seconds=on_time["seconds"])
            if on_time
            else timedelta(days=1)
        )

    def process_states_power(states_power: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
        """Convert state power values to Template objects where necessary."""
        return {
            key: Template(value, hass) if isinstance(value, str) and "{{" in value else value
            for key, value in normalize_states_power(states_power).items()
        }

    def process_daily_fixed_energy() -> None:
        """Process daily fixed energy configuration."""
        if CONF_DAILY_FIXED_ENERGY not in sensor_config:
            return

        daily_fixed_config = copy.copy(sensor_config[CONF_DAILY_FIXED_ENERGY])
        process_template(daily_fixed_config, CONF_VALUE_TEMPLATE, CONF_VALUE)
        process_on_time(daily_fixed_config)
        sensor_config[CONF_DAILY_FIXED_ENERGY] = daily_fixed_config

    def process_fixed_config() -> None:
        """Process fixed energy configuration."""
        if CONF_FIXED not in sensor_config:
            return

        fixed_config = copy.copy(sensor_config[CONF_FIXED])
        process_template(fixed_config, CONF_POWER_TEMPLATE, CONF_POWER)
        if CONF_STATES_POWER in fixed_config:
            fixed_config[CONF_STATES_POWER] = process_states_power(fixed_config[CONF_STATES_POWER])
        sensor_config[CONF_FIXED] = fixed_config

    def process_linear_config() -> None:
        """Process linear energy configuration."""
        if CONF_LINEAR not in sensor_config:
            return

        linear_config = copy.copy(sensor_config[CONF_LINEAR])
        sensor_config[CONF_LINEAR] = linear_config

    def process_calculation_enabled_condition() -> None:
        """Process calculation enabled condition template."""
        if CONF_CALCULATION_ENABLED_CONDITION in sensor_config:
            sensor_config[CONF_CALCULATION_ENABLED_CONDITION] = Template(
                sensor_config[CONF_CALCULATION_ENABLED_CONDITION],
                hass,
            )

    def process_utility_meter_offset() -> None:
        if CONF_UTILITY_METER_OFFSET in sensor_config:
            sensor_config[CONF_UTILITY_METER_OFFSET] = timedelta(days=sensor_config[CONF_UTILITY_METER_OFFSET])

    def process_playbook_config() -> None:
        if CONF_PLAYBOOK not in sensor_config:
            return
        playbook_config = copy.copy(sensor_config[CONF_PLAYBOOK])
        playbook_config[CONF_PLAYBOOKS] = normalize_playbooks(playbook_config[CONF_PLAYBOOKS])
        sensor_config[CONF_PLAYBOOK] = playbook_config

    handle_sensor_type()

    process_daily_fixed_energy()
    process_fixed_config()
    process_linear_config()
    process_playbook_config()
    process_calculation_enabled_condition()
    process_utility_meter_offset()

    return sensor_config
