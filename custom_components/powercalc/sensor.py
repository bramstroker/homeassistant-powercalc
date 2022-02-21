"""Platform for sensor integration."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Final, cast

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import (
    binary_sensor,
    climate,
    device_tracker,
    fan,
    humidifier,
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
from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.integration.sensor import INTEGRATION_METHOD
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.components.utility_meter import DEFAULT_OFFSET, max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    EVENT_HOMEASSISTANT_STARTED,
    POWER_WATT,
)
from homeassistant.core import callback
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import AddEntitiesCallback, split_entity_id
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from .common import create_source_entity, validate_name_pattern
from .const import (
    CALCULATION_MODES,
    CONF_AREA,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DAILY_FIXED_ENERGY,
    CONF_DISABLE_STANDBY_POWER,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_FIXED,
    CONF_GROUP,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_ON_TIME,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_STANDBY_POWER,
    CONF_TEMPLATE,
    CONF_UPDATE_FREQUENCY,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TYPES,
    CONF_VALUE,
    CONF_WLED,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERED_ENTITIES,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DOMAIN_CONFIG,
    DUMMY_ENTITY_ID,
)
from .errors import (
    PowercalcSetupError,
    SensorAlreadyConfiguredError,
    SensorConfigurationError,
)
from .model_discovery import is_supported_model
from .sensors.energy import (
    EnergySensor,
    create_daily_fixed_energy_sensor,
    create_energy_sensor,
)
from .sensors.group import GroupedEnergySensor, GroupedPowerSensor, GroupedSensor
from .sensors.power import PowerSensor, RealPowerSensor, create_power_sensor
from .sensors.utility_meter import create_utility_meters
from .strategy.fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from .strategy.linear import CONFIG_SCHEMA as LINEAR_SCHEMA
from .strategy.wled import CONFIG_SCHEMA as WLED_SCHEMA

_LOGGER = logging.getLogger(__name__)

SUPPORTED_ENTITY_DOMAINS = (
    light.DOMAIN,
    switch.DOMAIN,
    fan.DOMAIN,
    humidifier.DOMAIN,
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

DEFAULT_DAILY_UPDATE_FREQUENCY = 1800
MAX_GROUP_NESTING_LEVEL = 5

DAILY_FIXED_ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VALUE): vol.Any(vol.Coerce(float), cv.template),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=ENERGY_KILO_WATT_HOUR): vol.In(
            [ENERGY_KILO_WATT_HOUR, POWER_WATT]
        ),
        vol.Optional(CONF_ON_TIME, default=timedelta(days=1)): cv.time_period,
        vol.Optional(
            CONF_UPDATE_FREQUENCY, default=DEFAULT_DAILY_UPDATE_FREQUENCY
        ): vol.Coerce(int),
    }
)

SENSOR_CONFIG = {
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ENTITY_ID): cv.entity_domain(SUPPORTED_ENTITY_DOMAINS),
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_MODEL): cv.string,
    vol.Optional(CONF_MANUFACTURER): cv.string,
    vol.Optional(CONF_MODE): vol.In(CALCULATION_MODES),
    vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
    vol.Optional(CONF_DISABLE_STANDBY_POWER, default=False): cv.boolean,
    vol.Optional(CONF_CUSTOM_MODEL_DIRECTORY): cv.string,
    vol.Optional(CONF_POWER_SENSOR_ID): cv.entity_id,
    vol.Optional(CONF_FIXED): FIXED_SCHEMA,
    vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
    vol.Optional(CONF_WLED): WLED_SCHEMA,
    vol.Optional(CONF_DAILY_FIXED_ENERGY): DAILY_FIXED_ENERGY_SCHEMA,
    vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS): cv.boolean,
    vol.Optional(CONF_UTILITY_METER_TYPES): vol.All(
        cv.ensure_list, [vol.In(METER_TYPES)]
    ),
    vol.Optional(CONF_UTILITY_METER_OFFSET, default=DEFAULT_OFFSET): vol.All(
        cv.time_period, cv.positive_timedelta, max_28_days
    ),
    vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
    vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY, default=False): cv.boolean,
    vol.Optional(CONF_POWER_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_ENERGY_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_ENERGY_INTEGRATION_METHOD): vol.In(INTEGRATION_METHOD),
    vol.Optional(CONF_CREATE_GROUP): cv.string,
    vol.Optional(CONF_INCLUDE, default={}): vol.Schema(
        {
            vol.Optional(CONF_AREA): cv.string,
            vol.Optional(CONF_GROUP): cv.entity_id,
            vol.Optional(CONF_TEMPLATE): cv.template,
            vol.Optional(CONF_DOMAIN): cv.string,
        }
    ),
    vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE, default=False): cv.boolean,
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
            )
        }
    )
    return schema


SENSOR_CONFIG = build_nested_configuration_schema(SENSOR_CONFIG)

PLATFORM_SCHEMA: Final = vol.All(
    cv.has_at_least_one_key(
        CONF_ENTITY_ID, CONF_ENTITIES, CONF_INCLUDE, CONF_DAILY_FIXED_ENERGY
    ),
    PLATFORM_SCHEMA.extend(SENSOR_CONFIG),
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Set up the virtual power sensors."""

    try:
        entities = await create_sensors(hass, config, discovery_info)
    except SensorConfigurationError as err:
        _LOGGER.error(err)
        return

    if entities:
        async_add_entities(
            [entity for entity in entities[0] if isinstance(entity, SensorEntity)]
        )


def get_merged_sensor_configuration(*configs: dict, validate: bool = True) -> dict:
    """Merges configuration from multiple levels (sensor, group, global) into a single dict"""

    exclude_from_merging = [
        CONF_NAME,
        CONF_ENTITY_ID,
        CONF_UNIQUE_ID,
        CONF_POWER_SENSOR_ID,
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

    if not CONF_CREATE_ENERGY_SENSOR in merged_config:
        merged_config[CONF_CREATE_ENERGY_SENSOR] = merged_config.get(
            CONF_CREATE_ENERGY_SENSORS
        )

    if CONF_DAILY_FIXED_ENERGY in merged_config:
        merged_config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID

    if validate and not CONF_ENTITY_ID in merged_config:
        raise SensorConfigurationError(
            "You must supply an entity_id in the configuration, see the README"
        )

    return merged_config


async def create_sensors(
    hass: HomeAssistantType,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> tuple(list[SensorEntity, RealPowerSensor], list[SensorEntity, RealPowerSensor]):
    """Main routine to create all sensors (power, energy, utility, group) for a given entity"""

    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]

    if CONF_DAILY_FIXED_ENERGY in config:
        config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID

    # Setup a power sensor for one single appliance. Either by manual configuration or discovery
    if CONF_ENTITY_ID in config or discovery_info is not None:
        if discovery_info:
            config[CONF_ENTITY_ID] = discovery_info[CONF_ENTITY_ID]
        merged_sensor_config = get_merged_sensor_configuration(global_config, config)
        new_sensors = await create_individual_sensors(
            hass, merged_sensor_config, discovery_info
        )
        return (new_sensors, [])

    # Setup power sensors for multiple appliances in one config entry
    sensor_configs = {}
    new_sensors = []
    existing_sensors = []
    if CONF_ENTITIES in config:
        for entity_config in config[CONF_ENTITIES]:
            # When there are nested entities, combine these with the current entities, resursively
            if CONF_ENTITIES in entity_config:
                (child_new_sensors, child_existing_sensors) = await create_sensors(
                    hass, entity_config
                )
                new_sensors.extend(child_new_sensors)
                existing_sensors.extend(child_existing_sensors)
                continue

            entity_id = entity_config.get(CONF_ENTITY_ID) or str(uuid.uuid4())
            sensor_configs.update({entity_id: entity_config})

    # Automatically add a bunch of entities by area or evaluating template
    if CONF_INCLUDE in config:
        entities = resolve_include_entities(hass, config.get(CONF_INCLUDE))
        sensor_configs = {
            entity.entity_id: {CONF_ENTITY_ID: entity.entity_id}
            for entity in entities
            if entity and await is_supported_model(hass, entity)
        } | sensor_configs

    # Create sensors for each entity
    for sensor_config in sensor_configs.values():
        merged_sensor_config = get_merged_sensor_configuration(
            global_config, config, sensor_config
        )
        try:
            new_sensors.extend(
                await create_individual_sensors(hass, merged_sensor_config)
            )
        except SensorAlreadyConfiguredError as error:
            existing_sensors.extend(error.get_existing_entities())
        except SensorConfigurationError as error:
            _LOGGER.error(error)

    if not new_sensors and not existing_sensors:
        if CONF_CREATE_GROUP in config:
            raise SensorConfigurationError(
                f"Could not resolve any entities in group '{config.get(CONF_CREATE_GROUP)}'"
            )
        elif not sensor_configs:
            raise SensorConfigurationError(
                f"Could not resolve any entities for non-group sensor"
            )

    # Create group sensors (power, energy, utility)
    if CONF_CREATE_GROUP in config:
        group_entities = new_sensors + existing_sensors
        group_name = config.get(CONF_CREATE_GROUP)
        if not group_entities:
            _LOGGER.error("Could not create group %s, no entities resolved", group_name)
        group_sensors = await create_group_sensors(
            group_name,
            get_merged_sensor_configuration(global_config, config, validate=False),
            group_entities,
            hass=hass,
        )
        new_sensors.extend(group_sensors)

    return (new_sensors, existing_sensors)


async def create_individual_sensors(
    hass: HomeAssistantType,
    sensor_config: dict,
    discovery_info: DiscoveryInfoType | None = None,
) -> list[SensorEntity, RealPowerSensor]:
    """Create entities (power, energy, utility_meters) which track the appliance."""

    if discovery_info:
        source_entity = discovery_info.get(DISCOVERY_SOURCE_ENTITY)
    else:
        source_entity = await create_source_entity(sensor_config[CONF_ENTITY_ID], hass)

    if (
        source_entity.entity_id in hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES]
        and source_entity.entity_id != DUMMY_ENTITY_ID
    ):
        # Display an error when a power sensor was already configured for the same entity by the user
        # No log entry will be shown when the entity was auto discovered, we can silently continue
        if not discovery_info:
            existing_entities = hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES].get(
                source_entity.entity_id
            )
            raise SensorAlreadyConfiguredError(
                source_entity.entity_id, existing_entities
            )
        return []

    entities_to_add = []

    energy_sensor = None
    if CONF_DAILY_FIXED_ENERGY in sensor_config:
        energy_sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)
        entities_to_add.append(energy_sensor)

    else:
        try:
            power_sensor = await create_power_sensor(
                hass, sensor_config, source_entity, discovery_info
            )
        except PowercalcSetupError:
            return []

        entities_to_add.append(power_sensor)

        # Create energy sensor which integrates the power sensor
        if sensor_config.get(CONF_CREATE_ENERGY_SENSOR):
            energy_sensor = await create_energy_sensor(
                hass, sensor_config, power_sensor, source_entity
            )
            entities_to_add.append(energy_sensor)

    if energy_sensor:
        entities_to_add.extend(
            await create_utility_meters(hass, energy_sensor, sensor_config)
        )

    if discovery_info:
        hass.data[DOMAIN][DATA_DISCOVERED_ENTITIES].append(source_entity.entity_id)
    else:
        hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES].update(
            {source_entity.entity_id: entities_to_add}
        )

    if source_entity.entity_entry and source_entity.device_entry:
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            callback(
                lambda _: bind_entities_to_devices(
                    hass,
                    entities_to_add,
                    source_entity.device_entry.id,
                )
            ),
        )

    return entities_to_add


async def create_group_sensors(
    group_name: str,
    sensor_config: dict,
    entities: list[SensorEntity, RealPowerSensor],
    hass: HomeAssistantType,
) -> list[GroupedSensor]:
    """Create grouped power and energy sensors."""

    group_sensors = []

    power_sensors = list(
        filter(
            lambda elm: isinstance(elm, PowerSensor)
            and not isinstance(elm, GroupedPowerSensor),
            entities,
        )
    )
    power_sensor_ids = list(map(lambda x: x.entity_id, power_sensors))
    name_pattern = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    group_sensors.append(
        GroupedPowerSensor(
            name,
            power_sensor_ids,
            hass,
            unique_id=unique_id,
            rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION),
        )
    )
    _LOGGER.debug(f"Creating grouped power sensor: %s", name)

    energy_sensors = list(
        filter(
            lambda elm: isinstance(elm, EnergySensor)
            and not isinstance(elm, GroupedEnergySensor),
            entities,
        )
    )
    energy_sensor_ids = list(map(lambda x: x.entity_id, energy_sensors))
    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    energy_unique_id = None
    if unique_id:
        energy_unique_id = f"{unique_id}_energy"
    group_energy_sensor = GroupedEnergySensor(
        name,
        energy_sensor_ids,
        hass,
        unique_id=energy_unique_id,
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
    )
    group_sensors.append(group_energy_sensor)
    _LOGGER.debug("Creating grouped energy sensor: %s", name)

    group_sensors.extend(
        await create_utility_meters(hass, group_energy_sensor, sensor_config)
    )

    return group_sensors


def bind_entities_to_devices(hass: HomeAssistantType, entities, device_id: str):
    """Attach all the power/energy sensors to the same device as the source entity"""

    for entity in entities:
        ent_reg = entity_registry.async_get(hass)
        entity_entry = ent_reg.async_get(entity.entity_id)
        if (
            not entity_entry
            or entity_entry.platform != DOMAIN
            or entity_entry.device_id == device_id
        ):
            continue

        _LOGGER.debug(f"Binding {entity.entity_id} to device {device_id}")
        ent_reg.async_update_entity(entity.entity_id, device_id=device_id)


@callback
def resolve_include_entities(
    hass: HomeAssistantType, include_config: dict
) -> list[entity_registry.RegistryEntry]:
    entities = {}
    entity_reg = entity_registry.async_get(hass)

    # Include entities from a certain area
    if CONF_AREA in include_config:
        area_id = include_config.get(CONF_AREA)
        _LOGGER.debug("Including entities from area: %s", area_id)
        entities = entities | resolve_area_entities(hass, area_id)

    # Include entities from a certain domain
    if CONF_DOMAIN in include_config:
        domain = include_config.get(CONF_DOMAIN)
        _LOGGER.debug("Including entities from domain: %s", domain)
        entities = entities | {
            entity.entity_id: entity
            for entity in entity_reg.entities.values()
            if entity.domain == domain
        }

    # Include entities from a certain group
    if CONF_GROUP in include_config:
        group_id = include_config.get(CONF_GROUP)
        _LOGGER.debug("Including entities from area: %s", group_id)
        entities = entities | resolve_include_groups(hass, group_id)

    # Include entities by evaluating a template
    if CONF_TEMPLATE in include_config:
        template = include_config.get(CONF_TEMPLATE)
        if not isinstance(template, Template):
            raise SensorConfigurationError(
                "include->template is not a correct Template"
            )
        template.hass = hass

        _LOGGER.debug("Including entities from template")
        entity_ids = template.async_render()
        entities = entities | {
            entity_id: entity_reg.async_get(entity_id) for entity_id in entity_ids
        }

    return entities.values()


@callback
def resolve_include_groups(
    hass: HomeAssistantType, group_id: str
) -> dict[str, entity_registry.RegistryEntry]:
    """Get a listing of al entities in a given group"""
    entity_reg = entity_registry.async_get(hass)

    domain = split_entity_id(group_id)[0]
    if domain == LIGHT_DOMAIN:
        light_component = cast(EntityComponent, hass.data.get(LIGHT_DOMAIN))
        light_group = next(
            filter(
                lambda entity: entity.entity_id == group_id, light_component.entities
            ),
            None,
        )
        if light_group is None or light_group.platform.platform_name != GROUP_DOMAIN:
            raise SensorConfigurationError(f"Light group {group_id} not found")

        entity_ids = light_group.extra_state_attributes.get(ATTR_ENTITY_ID)
    else:
        group_state = hass.states.get(group_id)
        entity_ids = group_state.attributes.get(ATTR_ENTITY_ID)

    return {entity_id: entity_reg.async_get(entity_id) for entity_id in entity_ids}


@callback
def resolve_area_entities(
    hass: HomeAssistantType, area_id_or_name: str
) -> dict[str, entity_registry.RegistryEntry]:
    """Get a listing of al entities in a given area"""
    area_reg = area_registry.async_get(hass)
    area = area_reg.async_get_area(area_id_or_name)
    if area is None:
        area = area_reg.async_get_area_by_name(str(area_id_or_name))

    if area is None:
        raise SensorConfigurationError(
            f"No area with id or name '{area_id_or_name}' found in your HA instance"
        )

    area_id = area.id
    entity_reg = entity_registry.async_get(hass)

    entities = entity_registry.async_entries_for_area(entity_reg, area_id)

    device_reg = device_registry.async_get(hass)
    # We also need to add entities tied to a device in the area that don't themselves
    # have an area specified since they inherit the area from the device.
    entities.extend(
        [
            entity
            for device in device_registry.async_entries_for_area(device_reg, area_id)
            for entity in entity_registry.async_entries_for_device(
                entity_reg, device.id
            )
            if entity.area_id is None
        ]
    )
    return {
        entity.entity_id: entity for entity in entities if entity.domain == LIGHT_DOMAIN
    }
