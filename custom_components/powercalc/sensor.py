"""Platform for sensor integration."""

from __future__ import annotations

from collections.abc import Mapping
import copy
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any, cast
import uuid

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, PLATFORM_SCHEMA, SensorEntity
from homeassistant.components.utility_meter import max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_ID,
    CONF_NAME,
    CONF_PATH,
    CONF_UNIQUE_ID,
)
from homeassistant.core import Event, HomeAssistant, SupportsResponse, callback
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.entity_registry import (
    EVENT_ENTITY_REGISTRY_UPDATED,
    RegistryEntryDisabler,
)
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import voluptuous as vol

from . import DATA_GROUP_ENTITIES
from .analytics.analytics import collect_analytics
from .common import (
    SourceEntity,
    create_source_entity,
    get_merged_sensor_configuration,
    validate_is_number,
    validate_name_pattern,
)
from .const import (
    CONF_AND,
    CONF_AVAILABILITY_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_COMPOSITE,
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
    CONF_ON_TIME,
    CONF_OR,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_SUBTRACT_ENTITIES,
    CONF_UNAVAILABLE_POWER,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    CONF_VARIABLES,
    CONF_WLED,
    DATA_CONFIG_TYPES,
    DATA_CONFIGURED_ENTITIES,
    DATA_DOMAIN_ENTITIES,
    DATA_ENTITIES,
    DATA_HAS_GROUP_INCLUDE,
    DATA_SENSOR_TYPES,
    DATA_SOURCE_DOMAINS,
    DATA_USED_UNIQUE_IDS,
    DISCOVERY_TYPE,
    DOMAIN,
    DOMAIN_CONFIG,
    DUMMY_ENTITY_ID,
    ENERGY_INTEGRATION_METHODS,
    ENTITY_CATEGORIES,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    SERVICE_ACTIVATE_PLAYBOOK,
    SERVICE_CALIBRATE_ENERGY,
    SERVICE_CALIBRATE_UTILITY_METER,
    SERVICE_GET_ACTIVE_PLAYBOOK,
    SERVICE_GET_GROUP_ENTITIES,
    SERVICE_INCREASE_DAILY_ENERGY,
    SERVICE_RESET_ENERGY,
    SERVICE_STOP_PLAYBOOK,
    SERVICE_SWITCH_SUB_PROFILE,
    CalculationStrategy,
    GroupType,
    PowercalcDiscoveryType,
    SensorType,
    UnitPrefix,
)
from .device_binding import attach_entities_to_source_device
from .errors import (
    PowercalcSetupError,
    SensorAlreadyConfiguredError,
    SensorConfigurationError,
)
from .group_include.filter import FILTER_CONFIG, FilterOperator, create_composite_filter
from .group_include.include import find_entities
from .sensors.daily_energy import (
    DAILY_FIXED_ENERGY_SCHEMA,
    create_daily_fixed_energy_power_sensor,
    create_daily_fixed_energy_sensor,
)
from .sensors.energy import EnergySensor, create_energy_sensor
from .sensors.group.config_entry_utils import add_to_associated_groups
from .sensors.group.custom import GroupedSensor
from .sensors.group.factory import create_group_sensors
from .sensors.group.standby import StandbyPowerSensor
from .sensors.power import PowerSensor, VirtualPowerSensor, create_power_sensor
from .sensors.utility_meter import create_utility_meters
from .strategy.composite import CONFIG_SCHEMA as COMPOSITE_SCHEMA
from .strategy.fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from .strategy.linear import CONFIG_SCHEMA as LINEAR_SCHEMA
from .strategy.multi_switch import CONFIG_SCHEMA as MULTI_SWITCH_SCHEMA
from .strategy.playbook import CONFIG_SCHEMA as PLAYBOOK_SCHEMA
from .strategy.wled import CONFIG_SCHEMA as WLED_SCHEMA

_LOGGER = logging.getLogger(__name__)

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
    vol.Optional(CONF_FORCE_ENERGY_SENSOR_CREATION): cv.boolean,
    vol.Optional(CONF_FORCE_CALCULATE_GROUP_ENERGY): cv.boolean,
    vol.Optional(CONF_FIXED): FIXED_SCHEMA,
    vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
    vol.Optional(CONF_MULTI_SWITCH): MULTI_SWITCH_SCHEMA,
    vol.Optional(CONF_WLED): WLED_SCHEMA,
    vol.Optional(CONF_PLAYBOOK): PLAYBOOK_SCHEMA,
    vol.Optional(CONF_DAILY_FIXED_ENERGY): DAILY_FIXED_ENERGY_SCHEMA,  # type: ignore
    vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
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
    ),
    PLATFORM_SCHEMA.extend(SENSOR_CONFIG),
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Setup sensors from YAML config sensor entries."""

    # Legacy sensor platform config is used. Raise an issue.
    if not discovery_info and config:
        async_create_issue(
            hass,
            DOMAIN,
            "powercalc_deprecated_yaml",
            breaks_in_ha_version=None,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            learn_more_url="https://docs.powercalc.nl/configuration/migration/new-yaml-structure/",
            translation_key="deprecated_platform_yaml",
            translation_placeholders={"platform": SENSOR_DOMAIN},
        )

    if discovery_info:
        config = convert_discovery_info_to_sensor_config(discovery_info)

    if config.get(CONF_GROUP_TYPE) == GroupType.SUBTRACT:
        config[CONF_SENSOR_TYPE] = SensorType.GROUP

    if CONF_CREATE_GROUP in config:
        config[CONF_NAME] = config[CONF_CREATE_GROUP]

    register_entity_services()

    await _async_setup_entities(
        hass,
        config,
        async_add_entities,
        is_yaml=True,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup sensors from config entry (GUI config flow)."""

    if entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
        return

    sensor_config = convert_config_entry_to_sensor_config(entry, hass)

    if CONF_UNIQUE_ID not in sensor_config:
        sensor_config[CONF_UNIQUE_ID] = entry.unique_id

    if CONF_ENTITY_ID in sensor_config:
        _register_entity_id_change_listener(
            hass,
            entry,
            str(sensor_config.get(CONF_ENTITY_ID)),
        )

    await _async_setup_entities(
        hass,
        sensor_config,
        async_add_entities,
        config_entry=entry,
    )

    # Add entry to an existing group
    await add_to_associated_groups(hass, entry)


async def _async_setup_entities(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    config_entry: ConfigEntry | None = None,
    is_yaml: bool = False,
) -> None:
    """Main routine to setup power/energy sensors from provided configuration."""
    try:
        context = CreationContext(
            group=CONF_CREATE_GROUP in config,
            entity_config=config,
            is_yaml=is_yaml,
        )
        entities = await create_sensors(hass, config, context, config_entry)
        if config_entry:
            save_entity_ids_on_config_entry(hass, config_entry, entities)
    except SensorConfigurationError as err:
        _LOGGER.error(err)
        return

    await attach_entities_to_source_device(config_entry, entities.new, hass, None)

    entities_to_add = [entity for entity in entities.new if isinstance(entity, SensorEntity)]
    for entity in entities_to_add:
        if isinstance(entity, GroupedSensor | StandbyPowerSensor):
            hass.data[DOMAIN][DATA_GROUP_ENTITIES][entity.entity_id] = entity
        else:
            hass.data[DOMAIN][DATA_ENTITIES][entity.entity_id] = entity

    # See: https://github.com/bramstroker/homeassistant-powercalc/issues/1454
    # Remove entities which are disabled because of a disabled device from the list of entities to add
    # When we add nevertheless the entity_platform code will set device_id to None and abort entity addition.
    # `async_added_to_hass` hook will not be called, which powercalc uses to bind the entity to device again
    # This causes the powercalc entity to never be bound to the device again and be disabled forever.
    entity_reg = er.async_get(hass)
    for entity in entities_to_add:
        existing_entry = entity_reg.async_get(entity.entity_id)
        if existing_entry and existing_entry.disabled_by == RegistryEntryDisabler.DEVICE:
            entities_to_add.remove(entity)

    async_add_entities(entities_to_add)


def _register_entity_id_change_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
    source_entity_id: str,
) -> None:
    """
    When the user changes the entity id of the source entity,
    we also need to change the powercalc config entry to reflect these changes
    This method adds the necessary listener and handler to facilitate this
    """

    @callback
    async def _entity_rename_listener(event: Event) -> None:
        """Handle renaming of the entity"""
        old_entity_id = event.data["old_entity_id"]
        new_entity_id = event.data[CONF_ENTITY_ID]
        _LOGGER.debug(
            "Entity id has been changed, updating powercalc config. old_id=%s, new_id=%s",
            old_entity_id,
            new_entity_id,
        )
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_ENTITY_ID: new_entity_id},
        )

    @callback
    def _filter_entity_id(event: Mapping[str, Any] | Event) -> bool:
        """Only dispatch the listener for update events concerning the source entity"""

        # Breaking change in 2024.4.0, check for Event for versions prior to this
        if type(event) is Event:  # Intentionally avoid `isinstance` because it's slow and we trust `Event` is not subclassed
            event = event.data  # pragma: no cover
        return (
            event["action"] == "update"  # type: ignore
            and "old_entity_id" in event  # type: ignore
            and event["old_entity_id"] == source_entity_id  # type: ignore
        )

    hass.bus.async_listen(
        EVENT_ENTITY_REGISTRY_UPDATED,
        _entity_rename_listener,
        event_filter=_filter_entity_id,
    )


@callback
def save_entity_ids_on_config_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    entities: EntitiesBucket,
) -> None:
    """Save the power and energy sensor entity_id's on the config entry
    We need this in group sensor logic to differentiate between energy sensor and utility meters.
    """
    _LOGGER.debug("Saving entity ids on config entry %s", config_entry.entry_id)
    power_entities = [e.entity_id for e in entities.all() if isinstance(e, VirtualPowerSensor)]
    new_data = config_entry.data.copy()
    if power_entities:
        _LOGGER.debug("Setting power entity_id %s on config entry %s", power_entities[0], config_entry.entry_id)
        new_data.update({ENTRY_DATA_POWER_ENTITY: power_entities[0]})

    if bool(config_entry.data.get(CONF_CREATE_ENERGY_SENSOR, True)):
        energy_entities = [e.entity_id for e in entities.all() if isinstance(e, EnergySensor)]
        if not energy_entities:
            raise SensorConfigurationError(  # pragma: no cover
                f"No energy sensor created for config_entry {config_entry.entry_id}",
            )
        new_data.update({ENTRY_DATA_ENERGY_ENTITY: energy_entities[0]})
        _LOGGER.debug("Setting energy entity_id %s on config entry %s", energy_entities[0], config_entry.entry_id)
    elif ENTRY_DATA_ENERGY_ENTITY in new_data:
        _LOGGER.debug("Removing energy entity_id on config entry %s", config_entry.entry_id)
        new_data.pop(ENTRY_DATA_ENERGY_ENTITY)

    hass.config_entries.async_update_entry(
        config_entry,
        data=new_data,
    )


@callback
def register_entity_services() -> None:
    """Register the different entity services."""
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_RESET_ENERGY,
        {},
        "async_reset",
    )

    platform.async_register_entity_service(
        SERVICE_CALIBRATE_UTILITY_METER,
        {vol.Required(CONF_VALUE): validate_is_number},
        "async_calibrate",
    )

    platform.async_register_entity_service(
        SERVICE_CALIBRATE_ENERGY,
        {vol.Required(CONF_VALUE): validate_is_number},
        "async_calibrate",
    )

    platform.async_register_entity_service(
        SERVICE_INCREASE_DAILY_ENERGY,
        {vol.Required(CONF_VALUE): validate_is_number},
        "async_increase",
    )

    platform.async_register_entity_service(
        SERVICE_ACTIVATE_PLAYBOOK,
        {vol.Required("playbook_id"): cv.string},
        "async_activate_playbook",
    )

    platform.async_register_entity_service(
        SERVICE_STOP_PLAYBOOK,
        {},
        "async_stop_playbook",
    )

    platform.async_register_entity_service(
        SERVICE_GET_ACTIVE_PLAYBOOK,
        {},
        "get_active_playbook",
        supports_response=SupportsResponse.ONLY,
    )

    platform.async_register_entity_service(
        SERVICE_SWITCH_SUB_PROFILE,
        {vol.Required("profile"): cv.string},
        "async_switch_sub_profile",
    )

    platform.async_register_entity_service(
        SERVICE_GET_GROUP_ENTITIES,
        {},
        "get_group_entities",
        supports_response=SupportsResponse.ONLY,
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

    def process_template(config: dict, template_key: str, target_key: str) -> None:
        """Convert a template key in the config to a Template object."""
        if template_key in config:
            config[target_key] = Template(config[template_key], hass)
            del config[template_key]

    def process_on_time(config: dict) -> None:
        """Convert on_time dictionary to timedelta."""
        on_time = config.get(CONF_ON_TIME)
        config[CONF_ON_TIME] = (
            timedelta(hours=on_time["hours"], minutes=on_time["minutes"], seconds=on_time["seconds"]) if on_time else timedelta(days=1)
        )

    def process_states_power(states_power: dict) -> dict:
        """Convert state power values to Template objects where necessary."""
        return {key: Template(value, hass) if isinstance(value, str) and "{{" in value else value for key, value in states_power.items()}

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
        playbook_config[CONF_PLAYBOOKS] = {item[CONF_ID]: item[CONF_PATH] for item in playbook_config[CONF_PLAYBOOKS]}
        sensor_config[CONF_PLAYBOOK] = playbook_config

    handle_sensor_type()

    process_daily_fixed_energy()
    process_fixed_config()
    process_linear_config()
    process_playbook_config()
    process_calculation_enabled_condition()
    process_utility_meter_offset()

    return sensor_config


def convert_discovery_info_to_sensor_config(
    discovery_info: DiscoveryInfoType,
) -> ConfigType:
    """Convert discovery info to sensor config."""
    if discovery_info[DISCOVERY_TYPE] == PowercalcDiscoveryType.DOMAIN_GROUP:
        config = discovery_info
        config[CONF_GROUP_TYPE] = GroupType.DOMAIN
        config[CONF_SENSOR_TYPE] = SensorType.GROUP
        config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID
        return config

    if discovery_info[DISCOVERY_TYPE] == PowercalcDiscoveryType.STANDBY_GROUP:
        config = discovery_info
        config[CONF_GROUP_TYPE] = GroupType.STANDBY
        config[CONF_SENSOR_TYPE] = SensorType.GROUP
        config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID
        return config

    return discovery_info


async def create_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    context: CreationContext,
    config_entry: ConfigEntry | None = None,
) -> EntitiesBucket:
    """Main routine to create all sensors (power, energy, utility, group) for a given entity."""
    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]

    if is_individual_sensor_setup(config):
        return await setup_individual_sensors(hass, config, global_config, config_entry, context)

    sensor_configs: dict[str, ConfigType] = {}
    entities_to_add = EntitiesBucket()

    await setup_nested_or_group_sensors(hass, config, context, entities_to_add, sensor_configs)

    await add_discovered_entities(hass, config, entities_to_add, sensor_configs)

    await create_entities_sensors(hass, config, global_config, context, config_entry, sensor_configs, entities_to_add)

    if not entities_to_add.has_entities():
        log_missing_entities_warning(config)
        return entities_to_add

    await create_group_if_needed(hass, config, global_config, entities_to_add)

    return entities_to_add


def is_individual_sensor_setup(config: ConfigType) -> bool:
    """Check if the setup is for an individual sensor."""
    return CONF_ENTITIES not in config and CONF_INCLUDE not in config


async def setup_individual_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    global_config: ConfigType,
    config_entry: ConfigEntry | None,
    context: CreationContext,
) -> EntitiesBucket:
    """Set up an individual sensor."""
    merged_sensor_config = get_merged_sensor_configuration(global_config, config)
    sensor_type = SensorType(str(config.get(CONF_SENSOR_TYPE, SensorType.VIRTUAL_POWER)))

    # Collect runtime analytics data, for publishing later on.
    a = collect_analytics(hass, config_entry)
    a.inc(DATA_SENSOR_TYPES, sensor_type)
    a.inc(DATA_CONFIG_TYPES, "yaml" if context.is_yaml else "gui")

    if sensor_type == SensorType.GROUP:
        return EntitiesBucket(new=await create_group_sensors(hass, merged_sensor_config, config_entry))

    return await create_individual_sensors(hass, merged_sensor_config, context, config_entry)


async def setup_nested_or_group_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    context: CreationContext,
    entities_to_add: EntitiesBucket,
    sensor_configs: dict,
) -> None:
    """Set up sensors for nested or grouped entities."""
    for entity_config in config.get(CONF_ENTITIES, []):
        if CONF_ENTITIES in entity_config or context.group:
            await handle_nested_entity(hass, entity_config, context, entities_to_add)
        else:
            entity_id = entity_config.get(CONF_ENTITY_ID) or str(uuid.uuid4())
            sensor_configs[entity_id] = entity_config


async def handle_nested_entity(
    hass: HomeAssistant,
    entity_config: ConfigType,
    context: CreationContext,
    entities_to_add: EntitiesBucket,
) -> None:
    """Handle nested entities recursively."""
    try:
        child_entities = await create_sensors(
            hass,
            entity_config,
            context=CreationContext(
                group=context.group,
                entity_config=entity_config,
                is_yaml=context.is_yaml,
            ),
        )
        entities_to_add.extend_items(child_entities)
    except SensorConfigurationError as exception:
        _LOGGER.error(
            "Group state might be misbehaving because there was an error with an entity",
            exc_info=exception,
        )


async def add_discovered_entities(
    hass: HomeAssistant,
    config: ConfigType,
    entities_to_add: EntitiesBucket,
    sensor_configs: dict,
) -> None:
    """Add discovered entities based on include configuration."""
    if CONF_INCLUDE in config:
        collect_analytics(hass).set_flag(DATA_HAS_GROUP_INCLUDE)

        include_config: dict = cast(dict, config[CONF_INCLUDE])
        include_non_powercalc: bool = include_config.get(CONF_INCLUDE_NON_POWERCALC_SENSORS, True)
        entity_filter = create_composite_filter(include_config, hass, FilterOperator.AND)
        found_entities = await find_entities(hass, entity_filter, include_non_powercalc)
        entities_to_add.existing.extend(found_entities.resolved)
        for entity_id in found_entities.discoverable:
            sensor_configs[entity_id] = {CONF_ENTITY_ID: entity_id}


async def create_entities_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    global_config: ConfigType,
    context: CreationContext,
    config_entry: ConfigEntry | None,
    sensor_configs: dict,
    entities_to_add: EntitiesBucket,
) -> None:
    """Create sensors for each entity."""
    for sensor_config in sensor_configs.values():
        try:
            merged_sensor_config = get_merged_sensor_configuration(
                global_config,
                config,
                sensor_config,
            )
            entities_to_add.extend_items(
                await create_individual_sensors(
                    hass,
                    merged_sensor_config,
                    config_entry=config_entry,
                    context=CreationContext(
                        group=context.group,
                        entity_config=sensor_config,
                        is_yaml=context.is_yaml,
                    ),
                ),
            )
        except SensorConfigurationError as error:
            _LOGGER.error(error)


def log_missing_entities_warning(config: ConfigType) -> None:
    """Log a warning if no entities could be resolved."""
    log_message = "Could not resolve any entities"
    if CONF_CREATE_GROUP in config:
        log_message += f" in group '{config.get(CONF_CREATE_GROUP)}'"
    _LOGGER.warning(log_message)


async def create_group_if_needed(
    hass: HomeAssistant,
    config: ConfigType,
    global_config: ConfigType,
    entities_to_add: EntitiesBucket,
) -> None:
    """Create group sensors if required by the configuration."""
    if CONF_CREATE_GROUP not in config:
        return
    entities_to_add.new.extend(
        await create_group_sensors(
            hass,
            get_merged_sensor_configuration(global_config, config, validate=False),
            None,
            entities_to_add.all(),
        ),
    )


async def create_individual_sensors(
    hass: HomeAssistant,
    sensor_config: dict,
    context: CreationContext,
    config_entry: ConfigEntry | None = None,
) -> EntitiesBucket:
    """Create entities (power, energy, utility meters) which track the appliance."""

    source_entity = await create_source_entity(sensor_config[CONF_ENTITY_ID], hass)

    if (used_unique_ids := hass.data[DOMAIN].get(DATA_USED_UNIQUE_IDS)) is None:
        used_unique_ids = hass.data[DOMAIN][DATA_USED_UNIQUE_IDS] = []  # pragma: no cover

    try:
        await check_entity_not_already_configured(
            sensor_config,
            source_entity,
            hass,
            used_unique_ids,
            context,
        )
    except SensorAlreadyConfiguredError as error:
        # Include previously discovered/configured entities in group when no specific configuration
        if context.group and list(context.entity_config.keys()) == [CONF_ENTITY_ID]:
            return EntitiesBucket([], error.get_existing_entities())
        raise error

    entities_to_add: list[Entity] = []
    energy_sensor = await handle_energy_sensor_creation(hass, sensor_config, source_entity, entities_to_add)

    if not energy_sensor:
        try:
            power_sensor = await create_power_sensor(hass, sensor_config, source_entity, config_entry)
        except PowercalcSetupError:
            return EntitiesBucket()
        entities_to_add.append(power_sensor)
        energy_sensor = await create_energy_sensor_if_needed(hass, sensor_config, power_sensor, source_entity)
        if energy_sensor:
            entities_to_add.append(energy_sensor)
            attach_energy_sensor_to_power_sensor(power_sensor, energy_sensor)

    if energy_sensor:
        entities_to_add.extend(await create_utility_meters(hass, energy_sensor, sensor_config, config_entry))

    await attach_entities_to_source_device(config_entry, entities_to_add, hass, source_entity)

    update_registries(hass, source_entity, entities_to_add, context)
    unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
    if unique_id:
        used_unique_ids.append(unique_id)

    collect_analytics(hass, config_entry).inc(DATA_SOURCE_DOMAINS, source_entity.domain)

    return EntitiesBucket(new=entities_to_add, existing=[])


async def handle_energy_sensor_creation(
    hass: HomeAssistant,
    sensor_config: dict,
    source_entity: SourceEntity,
    entities_to_add: list[Entity],
) -> EnergySensor | None:
    """Handle the creation of an energy sensor if needed."""
    if CONF_DAILY_FIXED_ENERGY in sensor_config:
        energy_sensor = await create_daily_fixed_energy_sensor(hass, sensor_config, source_entity)
        entities_to_add.append(energy_sensor)
        if source_entity:
            daily_fixed_power_sensor = await create_daily_fixed_energy_power_sensor(hass, sensor_config, source_entity)
            if daily_fixed_power_sensor:
                entities_to_add.append(daily_fixed_power_sensor)
        return energy_sensor
    return None


async def create_energy_sensor_if_needed(
    hass: HomeAssistant,
    sensor_config: dict,
    power_sensor: PowerSensor,
    source_entity: SourceEntity,
) -> EnergySensor | None:
    """Create an energy sensor if it is needed."""
    if sensor_config.get(CONF_CREATE_ENERGY_SENSOR) or sensor_config.get(CONF_FORCE_ENERGY_SENSOR_CREATION) or CONF_ENERGY_SENSOR_ID in sensor_config:
        return await create_energy_sensor(hass, sensor_config, power_sensor, source_entity)
    return None


def attach_energy_sensor_to_power_sensor(power_sensor: Entity, energy_sensor: EnergySensor) -> None:
    """Attach the energy sensor to the power sensor."""
    if isinstance(power_sensor, VirtualPowerSensor):
        power_sensor.set_energy_sensor_attribute(energy_sensor.entity_id)


def update_registries(
    hass: HomeAssistant,
    source_entity: SourceEntity,
    entities_to_add: list[Entity],
    creation_context: CreationContext,
) -> None:
    """Update various registries with the new entities."""
    hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES].update(
        {source_entity.entity_id: [(entity, creation_context.is_yaml) for entity in entities_to_add]},
    )

    domain_entities = hass.data[DOMAIN][DATA_DOMAIN_ENTITIES].setdefault(source_entity.domain, [])
    domain_entities.extend(entities_to_add)


async def check_entity_not_already_configured(
    sensor_config: dict,
    source_entity: SourceEntity,
    hass: HomeAssistant,
    used_unique_ids: list[str],
    context: CreationContext,
) -> None:
    if source_entity.entity_id == DUMMY_ENTITY_ID:
        return

    entity_id = source_entity.entity_id
    configured_entities: dict[str, list[tuple[Entity, bool]]] = hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES]
    entities = configured_entities.get(entity_id, [])
    existing_entities = [e for e, _ in entities]
    unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id

    # Prevent duplicate unique_id within this creation run
    if unique_id in used_unique_ids:
        raise SensorAlreadyConfiguredError(entity_id, existing_entities)

    # UI flow cannot add when a YAML-defined entity already exists
    if not context.is_yaml and any(is_yaml for _, is_yaml in entities):
        raise SensorAlreadyConfiguredError(entity_id, existing_entities)

    # YAML flow without unique_id cannot add when any entity already exists
    if context.is_yaml and not sensor_config.get(CONF_UNIQUE_ID) and existing_entities:
        raise SensorAlreadyConfiguredError(entity_id, existing_entities)


@dataclass
class EntitiesBucket:
    new: list[Entity] = field(default_factory=list)
    existing: list[Entity] = field(default_factory=list)

    def extend_items(self, bucket: EntitiesBucket) -> None:
        """Append current entity bucket with new one"""
        self.new.extend(bucket.new)
        self.existing.extend(bucket.existing)

    def all(self) -> list[Entity]:
        """Return all entities both new and existing"""
        return self.new + self.existing

    def has_entities(self) -> bool:
        """Check whether the entity bucket is not empty"""
        return bool(self.new) or bool(self.existing)


@dataclass
class CreationContext:
    group: bool = field(default=False)
    entity_config: ConfigType = field(default_factory=dict)
    is_yaml: bool = field(default=False)
