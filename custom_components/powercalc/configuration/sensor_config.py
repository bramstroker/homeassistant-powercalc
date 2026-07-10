"""Sensor configuration schemas."""

from __future__ import annotations

from homeassistant.components.sensor import PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA
from homeassistant.components.utility_meter import max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from custom_components.powercalc.common import validate_name_pattern
from custom_components.powercalc.const import (
    CONF_AND,
    CONF_AVAILABILITY_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_COMPOSITE,
    CONF_COST,
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DAILY_FIXED_ENERGY,
    CONF_DELAY,
    CONF_DISABLE_STANDBY_POWER,
    CONF_ENERGY_FILTER_OUTLIER_ENABLED,
    CONF_ENERGY_FILTER_OUTLIER_MAX,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FILTER,
    CONF_FIXED,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_GROUP_ENERGY_START_AT_ZERO,
    CONF_GROUP_TYPE,
    CONF_HIDE_MEMBERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTI_SWITCH,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_NOT,
    CONF_OR,
    CONF_PLAYBOOK,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_NAMING,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_SUBTRACT_ENTITIES,
    CONF_UNAVAILABLE_POWER,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    CONF_VARIABLES,
    CONF_WLED,
    ENERGY_INTEGRATION_METHODS,
    ENTITY_CATEGORIES,
    CalculationStrategy,
    GroupType,
    UnitPrefix,
)
from custom_components.powercalc.group_include.filter import FILTER_CONFIG
from custom_components.powercalc.sensors.daily_energy import DAILY_FIXED_ENERGY_SCHEMA
from custom_components.powercalc.strategy.composite import CONFIG_SCHEMA as COMPOSITE_SCHEMA
from custom_components.powercalc.strategy.fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from custom_components.powercalc.strategy.linear import CONFIG_SCHEMA as LINEAR_SCHEMA
from custom_components.powercalc.strategy.multi_switch import CONFIG_SCHEMA as MULTI_SWITCH_SCHEMA
from custom_components.powercalc.strategy.playbook import CONFIG_SCHEMA as PLAYBOOK_SCHEMA
from custom_components.powercalc.strategy.wled import CONFIG_SCHEMA as WLED_SCHEMA

MAX_GROUP_NESTING_LEVEL = 5

SENSOR_CONFIG = {
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_AVAILABILITY_ENTITY): cv.entity_id,
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_MODEL): cv.string,
    vol.Optional(CONF_MANUFACTURER): cv.string,
    vol.Optional(CONF_MODE): vol.In([cls.value for cls in CalculationStrategy]),
    vol.Optional(CONF_STANDBY_POWER): vol.Any(vol.Coerce(float), cv.template),
    vol.Optional(CONF_DISABLE_STANDBY_POWER): cv.boolean,
    vol.Optional(CONF_CUSTOM_MODEL_DIRECTORY): cv.string,
    vol.Optional(CONF_POWER_SENSOR_ID): cv.entity_id,
    vol.Optional(CONF_COST): vol.Schema({vol.Required(CONF_ENERGY_SENSOR_ID): cv.entity_id}),
    vol.Optional(CONF_FORCE_ENERGY_SENSOR_CREATION): cv.boolean,
    vol.Optional(CONF_FORCE_CALCULATE_GROUP_ENERGY): cv.boolean,
    vol.Optional(CONF_FIXED): FIXED_SCHEMA,
    vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
    vol.Optional(CONF_MULTI_SWITCH): MULTI_SWITCH_SCHEMA,
    vol.Optional(CONF_WLED): WLED_SCHEMA,
    vol.Optional(CONF_PLAYBOOK): PLAYBOOK_SCHEMA,
    vol.Optional(CONF_DAILY_FIXED_ENERGY): DAILY_FIXED_ENERGY_SCHEMA,
    vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
    vol.Optional(CONF_CREATE_COST_SENSOR): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS): cv.boolean,
    vol.Optional(CONF_UTILITY_METER_NET_CONSUMPTION): cv.boolean,
    vol.Optional(CONF_UTILITY_METER_TARIFFS): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_UTILITY_METER_TYPES): vol.All(cv.ensure_list, [vol.In(METER_TYPES)]),
    vol.Optional(CONF_UTILITY_METER_OFFSET): vol.All(cv.time_period, cv.positive_timedelta, max_28_days),
    vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
    vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY): cv.boolean,
    vol.Optional(CONF_POWER_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_POWER_SENSOR_CATEGORY): vol.In(ENTITY_CATEGORIES),
    vol.Optional(CONF_ENERGY_SENSOR_ID): cv.entity_id,
    vol.Optional(CONF_ENERGY_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_ENERGY_SENSOR_CATEGORY): vol.In(ENTITY_CATEGORIES),
    vol.Optional(CONF_ENERGY_INTEGRATION_METHOD): vol.In(ENERGY_INTEGRATION_METHODS),
    vol.Optional(CONF_ENERGY_FILTER_OUTLIER_ENABLED): cv.boolean,
    vol.Optional(CONF_ENERGY_FILTER_OUTLIER_MAX): cv.positive_int,
    vol.Optional(CONF_ENERGY_SENSOR_UNIT_PREFIX): vol.In([cls.value for cls in UnitPrefix]),
    vol.Optional(CONF_CREATE_GROUP): cv.string,
    vol.Optional(CONF_GROUP_ENERGY_START_AT_ZERO): cv.boolean,
    vol.Optional(CONF_GROUP_TYPE): vol.In([cls.value for cls in GroupType]),
    vol.Optional(CONF_SUBTRACT_ENTITIES): vol.All(cv.ensure_list, [cv.entity_id]),
    vol.Optional(CONF_HIDE_MEMBERS): cv.boolean,
    vol.Optional(CONF_INCLUDE): vol.Schema(
        {
            **FILTER_CONFIG.schema,
            vol.Optional(CONF_FILTER): vol.Schema(
                {
                    **FILTER_CONFIG.schema,
                    vol.Optional(CONF_OR): vol.All(cv.ensure_list, [FILTER_CONFIG]),
                    vol.Optional(CONF_AND): vol.All(cv.ensure_list, [FILTER_CONFIG]),
                    vol.Optional(CONF_NOT): vol.All(cv.ensure_list, [FILTER_CONFIG]),
                },
            ),
            vol.Optional(CONF_INCLUDE_NON_POWERCALC_SENSORS, default=True): cv.boolean,
        },
    ),
    vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): cv.boolean,
    vol.Optional(CONF_CALCULATION_ENABLED_CONDITION): cv.template,
    vol.Optional(CONF_SLEEP_POWER): vol.Schema(
        {
            vol.Required(CONF_POWER): vol.Coerce(float),
            vol.Required(CONF_DELAY): cv.positive_int,
        },
    ),
    vol.Optional(CONF_UNAVAILABLE_POWER): vol.Coerce(float),
    vol.Optional(CONF_COMPOSITE): COMPOSITE_SCHEMA,
    vol.Optional(CONF_VARIABLES): vol.Schema({cv.string: cv.string}),
}


def build_nested_configuration_schema(schema: dict, iteration: int = 0) -> dict:
    if iteration == MAX_GROUP_NESTING_LEVEL:
        return schema
    iteration += 1
    schema.update(
        {
            vol.Optional(CONF_ENTITIES): vol.All(
                cv.ensure_list,
                [build_nested_configuration_schema(schema.copy(), iteration)],
            ),
        },
    )
    return schema


SENSOR_CONFIG = build_nested_configuration_schema(SENSOR_CONFIG)

PLATFORM_SCHEMA = vol.All(
    cv.has_at_least_one_key(
        CONF_ENTITY_ID,
        CONF_POWER_SENSOR_ID,
        CONF_ENTITIES,
        CONF_INCLUDE,
        CONF_DAILY_FIXED_ENERGY,
        CONF_COST,
    ),
    SENSOR_PLATFORM_SCHEMA.extend(SENSOR_CONFIG),
)
