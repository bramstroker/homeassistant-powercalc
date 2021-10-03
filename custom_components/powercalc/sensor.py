"""Platform for sensor integration."""

from __future__ import annotations

import logging
from typing import Final

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.components import (
    binary_sensor,
    climate,
    device_tracker,
    fan,
    input_boolean,
    input_number,
    input_select,
    light,
    media_player,
    remote,
    sensor,
    switch,
    vacuum,
    water_heater,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import split_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from .common import SourceEntity, validate_name_pattern
from .const import (
    CALCULATION_MODES,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DISABLE_STANDBY_POWER,
    CONF_DISABLE_STANDBY_USAGE,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER_SENSOR_NAMING,
    CONF_STANDBY_POWER,
    CONF_STANDBY_USAGE,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    DOMAIN_CONFIG,
)
from .errors import PowercalcSetupError, SensorConfigurationError
from .sensors.energy import VirtualEnergySensor, create_energy_sensor
from .sensors.group import GroupedEnergySensor, GroupedPowerSensor, GroupedSensor
from .sensors.power import VirtualPowerSensor, create_power_sensor
from .sensors.utility_meter import create_utility_meters
from .strategy_fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from .strategy_linear import CONFIG_SCHEMA as LINEAR_SCHEMA

_LOGGER = logging.getLogger(__name__)

SUPPORTED_ENTITY_DOMAINS = (
    light.DOMAIN,
    switch.DOMAIN,
    fan.DOMAIN,
    binary_sensor.DOMAIN,
    climate.DOMAIN,
    device_tracker.DOMAIN,
    remote.DOMAIN,
    media_player.DOMAIN,
    input_boolean.DOMAIN,
    input_number.DOMAIN,
    input_select.DOMAIN,
    sensor.DOMAIN,
    vacuum.DOMAIN,
    water_heater.DOMAIN,
)

SENSOR_CONFIG = {
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ENTITY_ID): cv.entity_domain(SUPPORTED_ENTITY_DOMAINS),
    vol.Optional(CONF_MODEL): cv.string,
    vol.Optional(CONF_MANUFACTURER): cv.string,
    vol.Optional(CONF_MODE): vol.In(CALCULATION_MODES),
    vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
    vol.Optional(CONF_DISABLE_STANDBY_POWER, default=False): cv.boolean,
    vol.Optional(CONF_STANDBY_USAGE): vol.Coerce(float),
    vol.Optional(CONF_DISABLE_STANDBY_USAGE, default=False): cv.boolean,
    vol.Optional(CONF_CUSTOM_MODEL_DIRECTORY): cv.string,
    vol.Optional(CONF_FIXED): FIXED_SCHEMA,
    vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
    vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS): cv.boolean,
    vol.Optional(CONF_UTILITY_METER_TYPES): vol.All(
        cv.ensure_list, [vol.In(METER_TYPES)]
    ),
    vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
    vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY, default=False): cv.boolean,
    vol.Optional(CONF_POWER_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_ENERGY_SENSOR_NAMING): validate_name_pattern,
}

GROUPED_SENSOR_CONFIG = {
    vol.Optional(CONF_CREATE_GROUP): cv.string,
    vol.Optional(CONF_ENTITIES, None): vol.All(cv.ensure_list, [SENSOR_CONFIG]),
}

PLATFORM_SCHEMA: Final = vol.All(
    cv.has_at_least_one_key(CONF_ENTITY_ID, CONF_ENTITIES),
    cv.deprecated(
        CONF_DISABLE_STANDBY_USAGE, replacement_key=CONF_DISABLE_STANDBY_POWER
    ),
    cv.deprecated(CONF_STANDBY_USAGE, replacement_key=CONF_STANDBY_POWER),
    PLATFORM_SCHEMA.extend(
        {
            **SENSOR_CONFIG,
            **GROUPED_SENSOR_CONFIG,
        }
    ),
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Set up the virtual power sensors."""

    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]

    entities = []
    try:
        if CONF_ENTITIES in config:
            for sensor_config in config.get(CONF_ENTITIES):
                merged_sensor_config = get_merged_sensor_configuration(
                    global_config, config, sensor_config
                )
                entities.extend(
                    await create_individual_sensors(hass, merged_sensor_config)
                )

            if CONF_CREATE_GROUP in config:
                group_name = config.get(CONF_CREATE_GROUP)
                group_sensors = create_group_sensors(
                    group_name, merged_sensor_config, entities, hass=hass
                )
                entities.extend(group_sensors)
        else:
            merged_sensor_config = get_merged_sensor_configuration(
                global_config, config
            )
            entities.extend(await create_individual_sensors(hass, merged_sensor_config))
    except SensorConfigurationError as err:
        _LOGGER.error(err)
        return

    if entities:
        async_add_entities(entities)


def get_merged_sensor_configuration(*configs: dict) -> dict:
    """Merges configuration from multiple levels (sensor, group, global) into a single dict"""

    merged_config = {}
    for config in configs:
        merged_config.update(config)

    if CONF_STANDBY_USAGE in merged_config:
        merged_config[CONF_STANDBY_POWER] = merged_config[CONF_STANDBY_USAGE]
    if CONF_DISABLE_STANDBY_USAGE in merged_config:
        merged_config[CONF_DISABLE_STANDBY_POWER] = merged_config[
            CONF_DISABLE_STANDBY_USAGE
        ]

    if not CONF_CREATE_ENERGY_SENSOR in merged_config:
        merged_config[CONF_CREATE_ENERGY_SENSOR] = merged_config.get(
            CONF_CREATE_ENERGY_SENSORS
        )

    if not CONF_ENTITY_ID in merged_config:
        raise SensorConfigurationError(
            "You must supply a entity_id in the configuration, see the README"
        )

    return merged_config


async def create_source_entity(entity_id: str, hass: HomeAssistantType) -> SourceEntity:
    """Create object containing all information about the source entity"""

    source_entity_domain, source_object_id = split_entity_id(entity_id)

    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(entity_id)

    unique_id = None
    supported_color_modes = []
    if entity_entry:
        source_entity_name = entity_entry.name or entity_entry.original_name
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id
        if entity_entry.capabilities:
            supported_color_modes = entity_entry.capabilities.get(
                light.ATTR_SUPPORTED_COLOR_MODES
            )
    else:
        source_entity_name = source_object_id.replace("_", " ")

    entity_state = hass.states.get(entity_id)
    if entity_state:
        source_entity_name = entity_state.name
        supported_color_modes = entity_state.attributes.get(
            light.ATTR_SUPPORTED_COLOR_MODES
        )

    return SourceEntity(
        unique_id,
        source_object_id,
        entity_id,
        source_entity_name,
        source_entity_domain,
        supported_color_modes or [],
        entity_entry,
    )


async def create_individual_sensors(
    hass: HomeAssistantType, sensor_config: dict
) -> list[SensorEntity]:
    """Create entities (power, energy, utility_meters) which track the appliance."""

    source_entity = await create_source_entity(sensor_config[CONF_ENTITY_ID], hass)

    try:
        power_sensor = await create_power_sensor(hass, sensor_config, source_entity)
    except PowercalcSetupError as err:
        return []

    entities_to_add = [power_sensor]

    if sensor_config.get(CONF_CREATE_ENERGY_SENSOR):
        energy_sensor = await create_energy_sensor(
            hass, sensor_config, power_sensor, source_entity
        )
        entities_to_add.append(energy_sensor)
        entities_to_add.extend(create_utility_meters(energy_sensor, sensor_config))

    return entities_to_add


def create_group_sensors(
    group_name: str,
    sensor_config: dict,
    entities: list[SensorEntity],
    hass: HomeAssistantType,
) -> list[GroupedSensor]:
    """Create grouped power and energy sensors."""

    group_sensors = []

    power_sensors = list(
        filter(lambda elm: isinstance(elm, VirtualPowerSensor), entities)
    )
    power_sensor_ids = list(map(lambda x: x.entity_id, power_sensors))
    name_pattern = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    group_sensors.append(GroupedPowerSensor(name, power_sensor_ids, hass))
    _LOGGER.debug("Creating grouped power sensor: %s", name)

    energy_sensors = list(
        filter(lambda elm: isinstance(elm, VirtualEnergySensor), entities)
    )
    energy_sensor_ids = list(map(lambda x: x.entity_id, energy_sensors))
    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    group_energy_sensor = GroupedEnergySensor(
        name, energy_sensor_ids, hass, rounding_digits=4
    )
    group_sensors.append(group_energy_sensor)
    _LOGGER.debug("Creating grouped energy sensor: %s", name)

    group_sensors.extend(create_utility_meters(group_energy_sensor, sensor_config))

    return group_sensors
