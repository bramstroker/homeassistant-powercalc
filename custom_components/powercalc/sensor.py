"""Platform for sensor integration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
from typing import Any, cast
import uuid

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorEntity
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
)
from homeassistant.core import Event, HomeAssistant, SupportsResponse, callback
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.entity_registry import (
    EVENT_ENTITY_REGISTRY_UPDATED,
    RegistryEntryDisabler,
)
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import voluptuous as vol

from . import DATA_GROUP_ENTITIES
from .analytics.analytics import collect_analytics
from .common import (
    SourceEntity,
    create_source_entity,
    get_merged_sensor_configuration,
    validate_is_number,
)
from .configuration.config_entry_conversion import convert_config_entry_to_sensor_config
from .configuration.discovery_info import convert_discovery_info_to_sensor_config
from .configuration.sensor_config import PLATFORM_SCHEMA as PLATFORM_SCHEMA
from .const import (
    CONF_COST,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_ID,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_GROUP_TYPE,
    CONF_INCLUDE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_SENSOR_TYPE,
    CONF_VALUE,
    DATA_CONFIG_TYPES,
    DATA_CONFIGURED_ENTITIES,
    DATA_DOMAIN_ENTITIES,
    DATA_ENTITIES,
    DATA_ENTITY_TYPES,
    DATA_HAS_GROUP_INCLUDE,
    DATA_SENSOR_TYPES,
    DATA_SOURCE_DOMAINS,
    DATA_USED_UNIQUE_IDS,
    DISCOVERY_TYPE,
    DOMAIN,
    DOMAIN_CONFIG,
    DUMMY_ENTITY_ID,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    SERVICE_ACTIVATE_PLAYBOOK,
    SERVICE_CALIBRATE_COST,
    SERVICE_CALIBRATE_ENERGY,
    SERVICE_CALIBRATE_UTILITY_METER,
    SERVICE_DEBUG_GROUP,
    SERVICE_GET_ACTIVE_PLAYBOOK,
    SERVICE_GET_GROUP_ENTITIES,
    SERVICE_INCREASE_DAILY_ENERGY,
    SERVICE_RESET_COST,
    SERVICE_RESET_ENERGY,
    SERVICE_STOP_PLAYBOOK,
    SERVICE_SWITCH_SUB_PROFILE,
    EntityType,
    GroupType,
    PowercalcDiscoveryType,
    SensorType,
)
from .device_binding import attach_entities_to_resolved_device
from .errors import (
    PowercalcSetupError,
    SensorAlreadyConfiguredError,
    SensorConfigurationError,
)
from .group_include.filter import FilterOperator, create_composite_filter
from .group_include.include import find_entities
from .sensors.cost import CostSensor, create_cost_sensor_for_energy_entity
from .sensors.daily_energy import (
    create_daily_fixed_energy_power_sensor,
    create_daily_fixed_energy_sensor,
)
from .sensors.energy import EnergySensor, create_energy_sensor
from .sensors.energy_related import create_energy_related_sensors
from .sensors.group.config_entry_utils import add_to_associated_groups
from .sensors.group.custom import GroupedSensor
from .sensors.group.factory import create_group_sensors
from .sensors.group.standby import StandbyPowerSensor
from .sensors.power import PowerSensor, VirtualPowerSensor, create_power_sensor

_LOGGER = logging.getLogger(__name__)

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

    await _async_setup_entities(
        hass,
        config,
        async_add_entities,
        is_yaml=True,
        discovery_type=discovery_info.get(DISCOVERY_TYPE) if discovery_info else None,
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
    discovery_type: PowercalcDiscoveryType | None = None,
) -> None:
    """Main routine to setup power/energy sensors from provided configuration."""

    register_entity_services()

    try:
        context = CreationContext(
            group=CONF_CREATE_GROUP in config,
            entity_config=config,
            is_yaml=is_yaml,
            discovery_type=discovery_type,
        )
        entities = await create_sensors(hass, config, context, config_entry)
        if config_entry:
            save_entity_ids_on_config_entry(hass, config_entry, entities)
    except SensorConfigurationError as err:
        _LOGGER.error(err)
        return

    await attach_entities_to_resolved_device(config_entry, entities.new, hass, None, config)

    entities_to_add = [entity for entity in entities.new if isinstance(entity, SensorEntity)]
    for entity in entities_to_add:
        if isinstance(entity, GroupedSensor | StandbyPowerSensor):
            hass.data[DOMAIN][DATA_GROUP_ENTITIES][entity.entity_id] = entity
        else:
            hass.data[DOMAIN][DATA_ENTITIES][entity.entity_id] = entity
            collect_analytics(hass, config_entry).inc(DATA_ENTITY_TYPES, _resolve_entity_type(entity))

    # See: https://github.com/bramstroker/homeassistant-powercalc/issues/1454
    # Remove entities which are disabled because of a disabled device from the list of entities to add
    # When we add nevertheless the entity_platform code will set device_id to None and abort entity addition.
    # `async_added_to_hass` will not be called, so BaseEntity cannot repair registry metadata.
    # This causes the powercalc entity to never be rebound and to stay disabled.
    entity_reg = er.async_get(hass)
    entities_to_add = [
        entity
        for entity in entities_to_add
        if not (
            (existing_entry := entity_reg.async_get(entity.entity_id))
            and existing_entry.disabled_by == RegistryEntryDisabler.DEVICE
        )
    ]

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
    def _entity_rename_listener(event: Event) -> None:
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
        event_data = event.data if isinstance(event, Event) else event
        return (
            event_data["action"] == "update"
            and "old_entity_id" in event_data
            and event_data["old_entity_id"] == source_entity_id
        )

    hass.bus.async_listen(
        EVENT_ENTITY_REGISTRY_UPDATED,
        _entity_rename_listener,
        event_filter=_filter_entity_id,
    )


def _resolve_entity_type(entity: Entity) -> EntityType:
    if isinstance(entity, UtilityMeterSensor):
        return EntityType.UTILITY_METER
    if isinstance(entity, CostSensor):
        return EntityType.COST_SENSOR
    if isinstance(entity, EnergySensor):
        return EntityType.ENERGY_SENSOR
    if isinstance(entity, PowerSensor):
        return EntityType.POWER_SENSOR
    return EntityType.UNKNOWN  # pragma: no cover


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
    if config_entry.data.get(CONF_SENSOR_TYPE) == SensorType.COST:
        # A standalone cost sensor entry has neither a power nor an energy sensor to track.
        return
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
        SERVICE_RESET_COST,
        {},
        "async_reset",
    )

    platform.async_register_entity_service(
        SERVICE_CALIBRATE_UTILITY_METER,
        {vol.Required(CONF_VALUE): validate_is_number},
        "async_calibrate",
    )

    platform.async_register_entity_service(
        SERVICE_CALIBRATE_COST,
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

    platform.async_register_entity_service(
        SERVICE_DEBUG_GROUP,
        {},
        "debug_group",
        supports_response=SupportsResponse.ONLY,
    )


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
    if CONF_COST in config:
        config[CONF_SENSOR_TYPE] = SensorType.COST

    sensor_type = resolve_sensor_type(config)
    merged_sensor_config = get_merged_sensor_configuration(global_config, config)

    if sensor_type == SensorType.GROUP:
        collect_sensor_analytics(hass, sensor_type, context.discovery_type, config_entry)
        return EntitiesBucket(new=await create_group_sensors(hass, merged_sensor_config, config_entry))

    if sensor_type == SensorType.COST:
        collect_sensor_analytics(hass, sensor_type, context.discovery_type, config_entry)
        cost_sensor = create_cost_sensor_for_energy_entity(hass, merged_sensor_config)
        return EntitiesBucket(new=[cost_sensor] if cost_sensor else [])

    return await create_individual_sensors(hass, merged_sensor_config, context, sensor_type, config_entry)


def resolve_sensor_type(config: ConfigType) -> SensorType:
    """Resolve the sensor type based on the configuration."""
    if CONF_COST in config:
        return SensorType.COST
    return SensorType(str(config.get(CONF_SENSOR_TYPE, SensorType.VIRTUAL_POWER)))


def collect_sensor_analytics(
    hass: HomeAssistant,
    sensor_type: SensorType,
    discovery_type: PowercalcDiscoveryType | None,
    config_entry: ConfigEntry | None = None,
) -> None:
    """Collect sensor analytics data."""
    a = collect_analytics(hass, config_entry)
    a.inc(DATA_SENSOR_TYPES, sensor_type)
    if discovery_type and discovery_type == PowercalcDiscoveryType.USER_YAML:
        a.inc(DATA_CONFIG_TYPES, "yaml")
    if config_entry:
        a.inc(DATA_CONFIG_TYPES, "gui")


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
                discovery_type=context.discovery_type,
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
                    sensor_type=merged_sensor_config.get(CONF_SENSOR_TYPE, SensorType.VIRTUAL_POWER),
                    context=CreationContext(
                        group=context.group,
                        entity_config=sensor_config,
                        is_yaml=context.is_yaml,
                        discovery_type=context.discovery_type,
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

    collect_sensor_analytics(hass, SensorType.GROUP, PowercalcDiscoveryType.USER_YAML)

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
    sensor_type: SensorType,
    config_entry: ConfigEntry | None = None,
) -> EntitiesBucket:
    """Create entities (power, energy, utility meters) which track the appliance."""

    source_entity = create_source_entity(sensor_config[CONF_ENTITY_ID], hass)

    # For device-based profiles, attach the device entry to the source entity
    source_entity = _attach_configured_device_entry(hass, sensor_config, source_entity)

    used_unique_ids = hass.data[DOMAIN].get(DATA_USED_UNIQUE_IDS, [])

    try:
        check_entity_not_already_configured(
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

    collect_sensor_analytics(hass, sensor_type, context.discovery_type, config_entry)

    entities_to_add: list[Entity] = []
    energy_sensor = await _create_daily_fixed_energy_sensors(hass, sensor_config, source_entity, entities_to_add)

    if not energy_sensor:
        try:
            power_sensor = await create_power_sensor(hass, sensor_config, source_entity, config_entry)
        except PowercalcSetupError:
            return EntitiesBucket()
        entities_to_add.append(power_sensor)
        if (
            sensor_config.get(CONF_CREATE_ENERGY_SENSOR)
            or sensor_config.get(CONF_FORCE_ENERGY_SENSOR_CREATION)
            or CONF_ENERGY_SENSOR_ID in sensor_config
        ):
            energy_sensor = create_energy_sensor(hass, sensor_config, power_sensor, source_entity)
            entities_to_add.append(energy_sensor)
            if isinstance(power_sensor, VirtualPowerSensor):
                power_sensor.set_energy_sensor_attribute(energy_sensor.entity_id)

    if energy_sensor:
        entities_to_add.extend(
            create_energy_related_sensors(hass, sensor_config, energy_sensor, source_entity, config_entry),
        )

    await attach_entities_to_resolved_device(config_entry, entities_to_add, hass, source_entity, sensor_config)
    hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES].update(
        {source_entity.entity_id: [(entity, context.is_yaml) for entity in entities_to_add]},
    )
    hass.data[DOMAIN][DATA_DOMAIN_ENTITIES].setdefault(source_entity.domain, []).extend(entities_to_add)

    unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
    if unique_id:
        used_unique_ids.append(unique_id)

    collect_analytics(hass, config_entry).inc(DATA_SOURCE_DOMAINS, source_entity.domain)

    return EntitiesBucket(new=entities_to_add, existing=[])


async def _create_daily_fixed_energy_sensors(
    hass: HomeAssistant,
    sensor_config: dict,
    source_entity: SourceEntity,
    entities_to_add: list[Entity],
) -> EnergySensor | None:
    if CONF_DAILY_FIXED_ENERGY not in sensor_config:
        return None

    energy_sensor = create_daily_fixed_energy_sensor(hass, sensor_config, source_entity)
    entities_to_add.append(energy_sensor)
    power_sensor = await create_daily_fixed_energy_power_sensor(hass, sensor_config, source_entity)
    if power_sensor:
        entities_to_add.append(power_sensor)
    return energy_sensor


def _attach_configured_device_entry(
    hass: HomeAssistant,
    sensor_config: dict,
    source_entity: SourceEntity,
) -> SourceEntity:
    if source_entity.entity_id != DUMMY_ENTITY_ID or "device" not in sensor_config:
        return source_entity

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(sensor_config["device"])
    if device_entry:
        return source_entity._replace(device_entry=device_entry)
    return source_entity


def check_entity_not_already_configured(
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
    discovery_type: PowercalcDiscoveryType | None = field(default=None)
