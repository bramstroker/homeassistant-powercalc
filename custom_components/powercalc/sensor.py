"""Platform for sensor integration."""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import timedelta
from typing import Any, Final, NamedTuple, Optional, cast

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
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
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.components.utility_meter import max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_platform,
    entity_registry,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import AddEntitiesCallback, split_entity_id
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .common import (
    SourceEntity,
    create_source_entity,
    get_merged_sensor_configuration,
    validate_is_number,
    validate_name_pattern,
)
from .const import (
    CONF_AREA,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CALIBRATE,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DAILY_FIXED_ENERGY,
    CONF_DISABLE_STANDBY_POWER,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_GROUP,
    CONF_HIDE_MEMBERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_ON_TIME,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_TEMPLATE,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    CONF_WLED,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERED_ENTITIES,
    DATA_DOMAIN_ENTITIES,
    DATA_USED_UNIQUE_IDS,
    DISCOVERY_SOURCE_ENTITY,
    DISCOVERY_TYPE,
    DOMAIN,
    DOMAIN_CONFIG,
    DUMMY_ENTITY_ID,
    ENERGY_INTEGRATION_METHODS,
    ENTITY_CATEGORIES,
    SERVICE_CALIBRATE_UTILITY_METER,
    SERVICE_RESET_ENERGY,
    CalculationStrategy,
    PowercalcDiscoveryType,
    SensorType,
    UnitPrefix,
)
from .errors import (
    PowercalcSetupError,
    SensorAlreadyConfiguredError,
    SensorConfigurationError,
)
from .power_profile.model_discovery import is_autoconfigurable
from .sensors.abstract import BaseEntity
from .sensors.daily_energy import (
    DAILY_FIXED_ENERGY_SCHEMA,
    create_daily_fixed_energy_power_sensor,
    create_daily_fixed_energy_sensor,
)
from .sensors.energy import create_energy_sensor
from .sensors.group import (
    create_group_sensors,
    create_group_sensors_from_config_entry,
    update_associated_group_entry,
)
from .sensors.power import RealPowerSensor, VirtualPowerSensor, create_power_sensor
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

MAX_GROUP_NESTING_LEVEL = 5

SENSOR_CONFIG = {
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ENTITY_ID): cv.entity_domain(SUPPORTED_ENTITY_DOMAINS),
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_MODEL): cv.string,
    vol.Optional(CONF_MANUFACTURER): cv.string,
    vol.Optional(CONF_MODE): vol.In([cls.value for cls in CalculationStrategy]),
    vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
    vol.Optional(CONF_DISABLE_STANDBY_POWER): cv.boolean,
    vol.Optional(CONF_CUSTOM_MODEL_DIRECTORY): cv.string,
    vol.Optional(CONF_POWER_SENSOR_ID): cv.entity_id,
    vol.Optional(CONF_FIXED): FIXED_SCHEMA,
    vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
    vol.Optional(CONF_WLED): WLED_SCHEMA,
    vol.Optional(CONF_DAILY_FIXED_ENERGY): DAILY_FIXED_ENERGY_SCHEMA,
    vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS): cv.boolean,
    vol.Optional(CONF_UTILITY_METER_TARIFFS): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_UTILITY_METER_TYPES): vol.All(
        cv.ensure_list, [vol.In(METER_TYPES)]
    ),
    vol.Optional(CONF_UTILITY_METER_OFFSET): vol.All(
        cv.time_period, cv.positive_timedelta, max_28_days
    ),
    vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
    vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY): cv.boolean,
    vol.Optional(CONF_POWER_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_POWER_SENSOR_CATEGORY): vol.In(ENTITY_CATEGORIES),
    vol.Optional(CONF_ENERGY_SENSOR_ID): cv.entity_id,
    vol.Optional(CONF_ENERGY_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_ENERGY_SENSOR_CATEGORY): vol.In(ENTITY_CATEGORIES),
    vol.Optional(CONF_ENERGY_INTEGRATION_METHOD): vol.In(ENERGY_INTEGRATION_METHODS),
    vol.Optional(CONF_ENERGY_SENSOR_UNIT_PREFIX): vol.In(
        [cls.value for cls in UnitPrefix]
    ),
    vol.Optional(CONF_CREATE_GROUP): cv.string,
    vol.Optional(CONF_HIDE_MEMBERS): cv.boolean,
    vol.Optional(CONF_INCLUDE): vol.Schema(
        {
            vol.Optional(CONF_AREA): cv.string,
            vol.Optional(CONF_GROUP): cv.entity_id,
            vol.Optional(CONF_TEMPLATE): cv.template,
            vol.Optional(CONF_DOMAIN): cv.string,
        }
    ),
    vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): cv.boolean,
    vol.Optional(CONF_CALCULATION_ENABLED_CONDITION): cv.template,
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

PLATFORM_SCHEMA: Final = vol.All(  # noqa: F811
    cv.has_at_least_one_key(
        CONF_ENTITY_ID, CONF_ENTITIES, CONF_INCLUDE, CONF_DAILY_FIXED_ENERGY
    ),
    PLATFORM_SCHEMA.extend(SENSOR_CONFIG),
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Setup sensors from YAML config sensor entries"""

    await _async_setup_entities(hass, config, async_add_entities, discovery_info)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup sensors from config entry (GUI config flow)"""
    sensor_config = convert_config_entry_to_sensor_config(entry)
    sensor_type = entry.data.get(CONF_SENSOR_TYPE)
    if sensor_type == SensorType.GROUP:
        global_config: dict = hass.data[DOMAIN][DOMAIN_CONFIG]
        merged_sensor_config = get_merged_sensor_configuration(
            global_config, sensor_config
        )
        entities = await create_group_sensors_from_config_entry(
            hass=hass, entry=entry, sensor_config=merged_sensor_config
        )
        async_add_entities(entities)
        return

    # Add entry to an existing group
    updated_group_entry = await update_associated_group_entry(hass, entry, remove=False)

    if CONF_UNIQUE_ID not in sensor_config:
        sensor_config[CONF_UNIQUE_ID] = entry.unique_id

    await _async_setup_entities(hass, sensor_config, async_add_entities)
    if updated_group_entry:
        await hass.config_entries.async_reload(updated_group_entry.entry_id)


async def _async_setup_entities(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Main routine to setup power/energy sensors from provided configuration"""

    register_entity_services()

    try:
        entities = await create_sensors(hass, config, discovery_info)
    except SensorConfigurationError as err:
        _LOGGER.error(err)
        return

    if entities:
        async_add_entities(
            [entity for entity in entities.new if isinstance(entity, SensorEntity)]
        )


@callback
def register_entity_services():
    """Register the different entity services"""
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_RESET_ENERGY,
        {},
        "async_reset_energy",
    )

    platform.async_register_entity_service(
        SERVICE_CALIBRATE_UTILITY_METER,
        {vol.Required(CONF_VALUE): validate_is_number},
        "async_calibrate",
    )


def convert_config_entry_to_sensor_config(config_entry: ConfigEntry) -> dict[str, Any]:
    """Convert the config entry structure to the sensor config which we use to create the entities"""
    sensor_config = dict(config_entry.data.copy())

    if sensor_config.get(CONF_SENSOR_TYPE) == SensorType.GROUP:
        sensor_config[CONF_CREATE_GROUP] = sensor_config.get(CONF_NAME)

    if CONF_DAILY_FIXED_ENERGY in sensor_config:
        daily_fixed_config = copy.copy(sensor_config.get(CONF_DAILY_FIXED_ENERGY))
        if CONF_VALUE_TEMPLATE in daily_fixed_config:
            daily_fixed_config[CONF_VALUE] = Template(
                daily_fixed_config[CONF_VALUE_TEMPLATE]
            )
            del daily_fixed_config[CONF_VALUE_TEMPLATE]
        if CONF_ON_TIME in daily_fixed_config:
            on_time = daily_fixed_config[CONF_ON_TIME]
            daily_fixed_config[CONF_ON_TIME] = timedelta(
                hours=on_time["hours"],
                minutes=on_time["minutes"],
                seconds=on_time["seconds"],
            )
        else:
            daily_fixed_config[CONF_ON_TIME] = timedelta(days=1)
        sensor_config[CONF_DAILY_FIXED_ENERGY] = daily_fixed_config

    if CONF_FIXED in sensor_config:
        fixed_config = copy.copy(sensor_config.get(CONF_FIXED))
        if CONF_POWER_TEMPLATE in fixed_config:
            fixed_config[CONF_POWER] = Template(fixed_config[CONF_POWER_TEMPLATE])
            del fixed_config[CONF_POWER_TEMPLATE]
        sensor_config[CONF_FIXED] = fixed_config

    if CONF_LINEAR in sensor_config:
        linear_config: dict[str, Any] = copy.copy(sensor_config.get(CONF_LINEAR))
        if CONF_CALIBRATE in linear_config:
            calibrate_dict: dict[str, float] = linear_config.get(CONF_CALIBRATE)
            new_calibrate_list = []
            for item in calibrate_dict.items():
                new_calibrate_list.append(f"{item[0]} -> {item[1]}")
            linear_config[CONF_CALIBRATE] = new_calibrate_list

        sensor_config[CONF_LINEAR] = linear_config

    if CONF_CALCULATION_ENABLED_CONDITION in sensor_config:
        sensor_config[CONF_CALCULATION_ENABLED_CONDITION] = Template(
            sensor_config[CONF_CALCULATION_ENABLED_CONDITION]
        )

    return sensor_config


async def create_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
    context: Optional[CreationContext] = None,
) -> EntitiesBucket:
    """Main routine to create all sensors (power, energy, utility, group) for a given entity"""

    if context is None:
        context = CreationContext(
            group=CONF_CREATE_GROUP in config, entity_config=config
        )

    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]

    # Handle setup of domain groups
    if (
        discovery_info
        and discovery_info[DISCOVERY_TYPE] == PowercalcDiscoveryType.DOMAIN_GROUP
    ):
        domain = discovery_info[CONF_DOMAIN]
        sensor_config = global_config.copy()
        sensor_config[
            CONF_UNIQUE_ID
        ] = f"powercalc_domaingroup_{discovery_info[CONF_DOMAIN]}"
        return EntitiesBucket(
            new=await create_group_sensors(
                f"All {domain}", sensor_config, discovery_info[CONF_ENTITIES], hass
            )
        )

    # Setup a power sensor for one single appliance. Either by manual configuration or discovery
    if (
        CONF_ENTITY_ID in config
        or discovery_info is not None
        or CONF_DAILY_FIXED_ENERGY in config
    ):
        if discovery_info:
            config[CONF_ENTITY_ID] = discovery_info[CONF_ENTITY_ID]
        merged_sensor_config = get_merged_sensor_configuration(global_config, config)
        return await create_individual_sensors(
            hass, merged_sensor_config, context, discovery_info
        )

    # Setup power sensors for multiple appliances in one config entry
    sensor_configs = {}
    new_sensors = []
    existing_sensors = []
    if CONF_ENTITIES in config:
        for entity_config in config[CONF_ENTITIES]:
            # When there are nested entities, combine these with the current entities, recursively
            if CONF_ENTITIES in entity_config or CONF_CREATE_GROUP in entity_config:
                try:
                    (child_new_sensors, child_existing_sensors) = await create_sensors(
                        hass, entity_config, context=context
                    )
                except SensorConfigurationError as err:
                    _LOGGER.error(err)
                    continue

                new_sensors.extend(child_new_sensors)
                existing_sensors.extend(child_existing_sensors)
                continue

            entity_id = entity_config.get(CONF_ENTITY_ID) or str(uuid.uuid4())
            sensor_configs.update({entity_id: entity_config})

    # Automatically add a bunch of entities by area or evaluating template
    if CONF_INCLUDE in config:
        entities = resolve_include_entities(hass, config.get(CONF_INCLUDE))
        _LOGGER.debug("Found include entities: %s", entities)
        sensor_configs = {
            entity.entity_id: {CONF_ENTITY_ID: entity.entity_id}
            for entity in entities
            if await is_autoconfigurable(hass, entity)
        } | sensor_configs

    # Create sensors for each entity
    for sensor_config in sensor_configs.values():
        context = CreationContext(group=context.group, entity_config=sensor_config)
        try:
            merged_sensor_config = get_merged_sensor_configuration(
                global_config, config, sensor_config
            )
            new_entities = await create_individual_sensors(
                hass, merged_sensor_config, context=context
            )
            new_sensors.extend(new_entities.new)
            existing_sensors.extend(new_entities.existing)
        except SensorConfigurationError as error:
            _LOGGER.error(error)

    if not new_sensors and not existing_sensors:
        if CONF_CREATE_GROUP in config:
            raise SensorConfigurationError(
                f"Could not resolve any entities in group '{config.get(CONF_CREATE_GROUP)}'"
            )
        elif not sensor_configs:
            raise SensorConfigurationError(
                "Could not resolve any entities for non-group sensor"
            )

    # Create group sensors (power, energy, utility)
    if CONF_CREATE_GROUP in config:
        group_entities = new_sensors + existing_sensors
        group_name = config.get(CONF_CREATE_GROUP)
        group_sensors = await create_group_sensors(
            group_name,
            get_merged_sensor_configuration(global_config, config, validate=False),
            group_entities,
            hass=hass,
        )
        new_sensors.extend(group_sensors)

    return EntitiesBucket(new=new_sensors, existing=existing_sensors)


async def create_individual_sensors(  # noqa: C901
    hass: HomeAssistant,
    sensor_config: dict,
    context: CreationContext,
    discovery_info: DiscoveryInfoType | None = None,
) -> EntitiesBucket:
    """Create entities (power, energy, utility_meters) which track the appliance."""

    if discovery_info:
        source_entity: SourceEntity = discovery_info.get(DISCOVERY_SOURCE_ENTITY)
    else:
        source_entity = await create_source_entity(sensor_config[CONF_ENTITY_ID], hass)

    if (used_unique_ids := hass.data[DOMAIN].get(DATA_USED_UNIQUE_IDS)) is None:
        used_unique_ids = hass.data[DOMAIN][DATA_USED_UNIQUE_IDS] = []
    try:
        await check_entity_not_already_configured(
            sensor_config,
            source_entity,
            hass,
            used_unique_ids,
            discovery_info is not None,
        )
    except SensorAlreadyConfiguredError as error:
        # Include previously discovered/configured entities in group when no specific configuration
        if context.group and list(context.entity_config.keys()) == [CONF_ENTITY_ID]:
            return EntitiesBucket([], error.existing_entities)
        if discovery_info:
            return EntitiesBucket()
        raise error

    entities_to_add: list[BaseEntity] = []

    energy_sensor = None
    if CONF_DAILY_FIXED_ENERGY in sensor_config:
        energy_sensor = await create_daily_fixed_energy_sensor(
            hass, sensor_config, source_entity
        )
        entities_to_add.append(energy_sensor)
        power_sensor = await create_daily_fixed_energy_power_sensor(
            hass, sensor_config, source_entity
        )
        if power_sensor:
            entities_to_add.append(power_sensor)

    else:
        try:
            power_sensor = await create_power_sensor(
                hass, sensor_config, source_entity, discovery_info
            )
        except PowercalcSetupError:
            return EntitiesBucket()

        entities_to_add.append(power_sensor)

        # Create energy sensor which integrates the power sensor
        if sensor_config.get(CONF_CREATE_ENERGY_SENSOR):
            energy_sensor = await create_energy_sensor(
                hass, sensor_config, power_sensor, source_entity
            )
            entities_to_add.append(energy_sensor)
            if isinstance(power_sensor, VirtualPowerSensor) and isinstance(
                energy_sensor, SensorEntity
            ):
                power_sensor.set_energy_sensor_attribute(energy_sensor.entity_id)

    if energy_sensor:
        entities_to_add.extend(
            await create_utility_meters(hass, energy_sensor, sensor_config)
        )

    # Set the entity to same device as the source entity, if any available
    if source_entity.entity_entry and source_entity.device_entry:
        for entity in entities_to_add:
            if not isinstance(entity, BaseEntity):
                continue
            try:
                setattr(entity, "device_id", source_entity.device_entry.id)
            except AttributeError:
                _LOGGER.error(f"{entity.entity_id}: Cannot set device id on entity")

    # Update several registries
    if discovery_info:
        hass.data[DOMAIN][DATA_DISCOVERED_ENTITIES].update(
            {source_entity.entity_id: entities_to_add}
        )
    else:
        hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES].update(
            {source_entity.entity_id: entities_to_add}
        )

    if source_entity.domain not in hass.data[DOMAIN][DATA_DOMAIN_ENTITIES]:
        hass.data[DOMAIN][DATA_DOMAIN_ENTITIES][source_entity.domain] = []

    hass.data[DOMAIN][DATA_DOMAIN_ENTITIES][source_entity.domain].extend(
        entities_to_add
    )

    # Keep track for which unique_id's we generated sensors already
    unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
    if unique_id:
        used_unique_ids.append(unique_id)

    return EntitiesBucket(new=entities_to_add, existing=[])


async def check_entity_not_already_configured(
    sensor_config: dict,
    source_entity: SourceEntity,
    hass: HomeAssistant,
    used_unique_ids: list[str],
    is_discovered: True,
):
    if source_entity.entity_id == DUMMY_ENTITY_ID:
        return

    configured_entities: dict[str, list[SensorEntity]] = hass.data[DOMAIN][
        DATA_CONFIGURED_ENTITIES
    ]
    discovered_entities: dict[str, list[SensorEntity]] = hass.data[DOMAIN][
        DATA_DISCOVERED_ENTITIES
    ]

    # Prefer configured entity over discovered entity
    if not is_discovered and source_entity.entity_id in discovered_entities:
        entity_reg = er.async_get(hass)
        for entity in discovered_entities.get(source_entity.entity_id):
            entity_reg.async_remove(entity.entity_id)
            hass.states.async_remove(entity.entity_id)
        discovered_entities[source_entity.entity_id] = []
        return

    existing_entities = (
        configured_entities.get(source_entity.entity_id)
        or discovered_entities.get(source_entity.entity_id)
        or []
    )

    unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
    if unique_id and unique_id in used_unique_ids:
        raise SensorAlreadyConfiguredError(source_entity.entity_id, existing_entities)

    if unique_id is None and source_entity.entity_id in existing_entities:
        raise SensorAlreadyConfiguredError(source_entity.entity_id, existing_entities)


@callback
def resolve_include_entities(
    hass: HomeAssistant, include_config: dict
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
        _LOGGER.debug("Including entities from group: %s", group_id)
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

    return list(entities.values())


@callback
def resolve_include_groups(
    hass: HomeAssistant, group_id: str
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
        if group_state is None:
            raise SensorConfigurationError(f"Group state {group_id} not found")
        entity_ids = group_state.attributes.get(ATTR_ENTITY_ID)

    return {entity_id: entity_reg.async_get(entity_id) for entity_id in entity_ids}


@callback
def resolve_area_entities(
    hass: HomeAssistant, area_id_or_name: str
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


class EntitiesBucket(NamedTuple):
    new: list[Entity, RealPowerSensor] = []
    existing: list[Entity, RealPowerSensor] = []


class CreationContext(NamedTuple):
    group: bool = False
    entity_config: ConfigType = {}
