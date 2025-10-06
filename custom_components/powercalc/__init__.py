"""The PowerCalc integration."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter import DEFAULT_OFFSET, max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_STARTED,
    EntityCategory,
    Platform,
)
from homeassistant.const import __version__ as HA_VERSION  # noqa: N812
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.typing import ConfigType

from .common import validate_name_pattern
from .const import (
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_LIBRARY_DOWNLOAD,
    CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES,
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_GROUP_UPDATE_INTERVAL,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_PLAYBOOK,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_SENSORS,
    CONF_STATE_TRIGGER,
    CONF_STATES_TRIGGER,
    CONF_UNAVAILABLE_POWER,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERY_MANAGER,
    DATA_DOMAIN_ENTITIES,
    DATA_ENTITIES,
    DATA_GROUP_ENTITIES,
    DATA_STANDBY_POWER_SENSORS,
    DATA_USED_UNIQUE_IDS,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENERGY_UNIT_PREFIX,
    DEFAULT_ENTITY_CATEGORY,
    DEFAULT_GROUP_UPDATE_INTERVAL,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_POWER_SENSOR_PRECISION,
    DEFAULT_UPDATE_FREQUENCY,
    DEFAULT_UTILITY_METER_TYPES,
    DISCOVERY_TYPE,
    DOMAIN,
    DOMAIN_CONFIG,
    ENERGY_INTEGRATION_METHODS,
    ENTITY_CATEGORIES,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    MIN_HA_VERSION,
    SERVICE_CHANGE_GUI_CONFIGURATION,
    SERVICE_RELOAD,
    SERVICE_UPDATE_LIBRARY,
    PowercalcDiscoveryType,
    SensorType,
    UnitPrefix,
)
from .discovery import DiscoveryManager
from .power_profile.power_profile import DeviceType
from .sensor import SENSOR_CONFIG
from .sensors.group.config_entry_utils import (
    get_entries_having_subgroup,
    remove_group_from_power_sensor_entry,
    remove_power_sensor_from_associated_groups,
)
from .service.gui_configuration import SERVICE_SCHEMA, change_gui_configuration

PLATFORMS = [Platform.SENSOR]

FLAG_HAS_GLOBAL_GUI_CONFIG = "has_global_gui_config"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.deprecated(
                CONF_SCAN_INTERVAL,
                replacement_key=CONF_FORCE_UPDATE_FREQUENCY,
            ),
            vol.Schema(
                {
                    vol.Optional(
                        CONF_FORCE_UPDATE_FREQUENCY,
                        default=DEFAULT_UPDATE_FREQUENCY,
                    ): cv.time_period,
                    vol.Optional(
                        CONF_GROUP_UPDATE_INTERVAL,
                        default=DEFAULT_GROUP_UPDATE_INTERVAL,
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_POWER_SENSOR_NAMING,
                        default=DEFAULT_POWER_NAME_PATTERN,
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_POWER_SENSOR_FRIENDLY_NAMING,
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_POWER_SENSOR_CATEGORY,
                        default=DEFAULT_ENTITY_CATEGORY,
                    ): vol.In(ENTITY_CATEGORIES),
                    vol.Optional(
                        CONF_ENERGY_SENSOR_NAMING,
                        default=DEFAULT_ENERGY_NAME_PATTERN,
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_ENERGY_SENSOR_CATEGORY,
                        default=DEFAULT_ENTITY_CATEGORY,
                    ): vol.In(ENTITY_CATEGORIES),
                    vol.Optional(
                        CONF_DISABLE_EXTENDED_ATTRIBUTES,
                        default=False,
                    ): cv.boolean,
                    vol.Optional(
                        CONF_DISABLE_LIBRARY_DOWNLOAD,
                        default=False,
                    ): cv.boolean,
                    vol.Optional(CONF_ENABLE_AUTODISCOVERY, default=True): cv.boolean,
                    vol.Optional(CONF_CREATE_ENERGY_SENSORS, default=True): cv.boolean,
                    vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): cv.boolean,
                    vol.Optional(CONF_UTILITY_METER_TARIFFS, default=[]): vol.All(
                        cv.ensure_list,
                        [cv.string],
                    ),
                    vol.Optional(
                        CONF_UTILITY_METER_TYPES,
                        default=DEFAULT_UTILITY_METER_TYPES,
                    ): vol.All(cv.ensure_list, [vol.In(METER_TYPES)]),
                    vol.Optional(
                        CONF_UTILITY_METER_OFFSET,
                        default=DEFAULT_OFFSET,
                    ): vol.All(cv.time_period, cv.positive_timedelta, max_28_days),
                    vol.Optional(
                        CONF_ENERGY_INTEGRATION_METHOD,
                        default=DEFAULT_ENERGY_INTEGRATION_METHOD,
                    ): vol.In(ENERGY_INTEGRATION_METHODS),
                    vol.Optional(
                        CONF_ENERGY_SENSOR_PRECISION,
                        default=DEFAULT_ENERGY_SENSOR_PRECISION,
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_POWER_SENSOR_PRECISION,
                        default=DEFAULT_POWER_SENSOR_PRECISION,
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_ENERGY_SENSOR_UNIT_PREFIX,
                        default=UnitPrefix.KILO,
                    ): vol.In([cls.value for cls in UnitPrefix]),
                    vol.Optional(CONF_CREATE_DOMAIN_GROUPS, default=[]): vol.All(
                        cv.ensure_list,
                        [cv.string],
                    ),
                    vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): cv.boolean,
                    vol.Optional(CONF_UNAVAILABLE_POWER): vol.Coerce(float),
                    vol.Optional(CONF_SENSORS): vol.All(
                        cv.ensure_list,
                        [SENSOR_CONFIG],
                    ),
                    vol.Optional(CONF_INCLUDE_NON_POWERCALC_SENSORS): cv.boolean,
                    vol.Optional(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES): vol.All(
                        cv.ensure_list,
                        [cls.value for cls in DeviceType],
                    ),
                    vol.Optional(CONF_DISCOVERY_EXCLUDE_SELF_USAGE, default=False): cv.boolean,
                },
            ),
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):  # pragma: no cover
        msg = (
            "This integration requires at least HomeAssistant version "
            f" {MIN_HA_VERSION}, you are running version {HA_VERSION}."
            " Please upgrade HomeAssistant to continue use this integration."
        )
        _notify_message(hass, "inv_ha_version", "PowerCalc", msg)
        _LOGGER.critical(msg)
        return False

    global_config = get_global_configuration(hass, config)

    discovery_manager = await create_discovery_manager_instance(hass, config, global_config)
    hass.data[DOMAIN] = {
        DATA_DISCOVERY_MANAGER: discovery_manager,
        DOMAIN_CONFIG: global_config,
        DATA_CONFIGURED_ENTITIES: {},
        DATA_DOMAIN_ENTITIES: {},
        DATA_GROUP_ENTITIES: {},
        DATA_ENTITIES: {},
        DATA_USED_UNIQUE_IDS: [],
        DATA_STANDBY_POWER_SENSORS: {},
    }

    await register_services(hass)
    await setup_yaml_sensors(hass, config, global_config)

    setup_domain_groups(hass, global_config)
    setup_standby_group(hass, global_config)

    try:
        await repair_none_config_entries_issue(hass)
    except Exception as e:  # noqa: BLE001  # pragma: no cover
        _LOGGER.error("problem while cleaning up None entities", exc_info=e)  # pragma: no cover

    return True


async def create_discovery_manager_instance(
    hass: HomeAssistant,
    ha_config: ConfigType,
    global_powercalc_config: ConfigType,
) -> DiscoveryManager:
    exclude_device_types = [DeviceType(device_type) for device_type in global_powercalc_config.get(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES, [])]
    exclude_self_usage = global_powercalc_config.get(CONF_DISCOVERY_EXCLUDE_SELF_USAGE, False)

    manager = DiscoveryManager(
        hass,
        ha_config,
        exclude_device_types=exclude_device_types,
        exclude_self_usage_profiles=exclude_self_usage,
    )
    if global_powercalc_config.get(CONF_ENABLE_AUTODISCOVERY):
        await manager.setup()
    return manager


def get_global_configuration(hass: HomeAssistant, config: ConfigType) -> ConfigType:
    global_config = config.get(DOMAIN) or {
        CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
        CONF_POWER_SENSOR_PRECISION: DEFAULT_POWER_SENSOR_PRECISION,
        CONF_POWER_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
        CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
        CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
        CONF_ENERGY_SENSOR_PRECISION: DEFAULT_ENERGY_SENSOR_PRECISION,
        CONF_ENERGY_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
        CONF_ENERGY_SENSOR_UNIT_PREFIX: DEFAULT_ENERGY_UNIT_PREFIX,
        CONF_FORCE_UPDATE_FREQUENCY: DEFAULT_UPDATE_FREQUENCY,
        CONF_GROUP_UPDATE_INTERVAL: DEFAULT_GROUP_UPDATE_INTERVAL,
        CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
        CONF_IGNORE_UNAVAILABLE_STATE: False,
        CONF_CREATE_DOMAIN_GROUPS: [],
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_ENABLE_AUTODISCOVERY: True,
        CONF_UTILITY_METER_OFFSET: DEFAULT_OFFSET,
        CONF_UTILITY_METER_TYPES: DEFAULT_UTILITY_METER_TYPES,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
    }

    global_config_entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, ENTRY_GLOBAL_CONFIG_UNIQUE_ID)
    if global_config_entry:
        _LOGGER.debug("Found global configuration entry: %s", global_config_entry.data)
        global_config.update(get_global_gui_configuration(global_config_entry))

    return global_config


def get_global_gui_configuration(config_entry: ConfigEntry) -> ConfigType:
    global_config = dict(config_entry.data)
    if CONF_FORCE_UPDATE_FREQUENCY in global_config:
        global_config[CONF_FORCE_UPDATE_FREQUENCY] = timedelta(seconds=global_config[CONF_FORCE_UPDATE_FREQUENCY])
    if CONF_UTILITY_METER_OFFSET in global_config:
        global_config[CONF_UTILITY_METER_OFFSET] = timedelta(days=global_config[CONF_UTILITY_METER_OFFSET])
    if global_config.get(CONF_ENERGY_SENSOR_CATEGORY):
        global_config[CONF_ENERGY_SENSOR_CATEGORY] = EntityCategory(global_config[CONF_ENERGY_SENSOR_CATEGORY])
    if global_config.get(CONF_POWER_SENSOR_CATEGORY):
        global_config[CONF_POWER_SENSOR_CATEGORY] = EntityCategory(global_config[CONF_POWER_SENSOR_CATEGORY])
    global_config[FLAG_HAS_GLOBAL_GUI_CONFIG] = True

    return global_config


async def register_services(hass: HomeAssistant) -> None:
    """Register generic services"""

    async def _handle_change_gui_service(call: ServiceCall) -> None:
        await change_gui_configuration(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHANGE_GUI_CONFIGURATION,
        _handle_change_gui_service,
        schema=SERVICE_SCHEMA,
    )

    async def _handle_update_library_service(_: ServiceCall) -> None:
        _LOGGER.info("Updating library and rediscovering devices")
        discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]
        await discovery_manager.update_library_and_rediscover()

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_LIBRARY,
        _handle_update_library_service,
    )

    async def _reload_config(_: ServiceCall) -> None:
        """Reload powercalc."""
        reload_config = await async_integration_yaml_config(hass, DOMAIN)
        reset_platforms = async_get_platforms(hass, DOMAIN)
        for reset_platform in reset_platforms:
            await reset_platform.async_reset()
        if not reload_config:
            return

        hass.data[DOMAIN][DATA_USED_UNIQUE_IDS] = []
        hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES] = {}
        hass.data[DOMAIN][DOMAIN_CONFIG] = get_global_configuration(hass, reload_config)

        # Reload YAML sensors if any
        if DOMAIN in reload_config:
            for sensor_config in reload_config[DOMAIN].get(CONF_SENSORS, []):
                sensor_config.update({DISCOVERY_TYPE: PowercalcDiscoveryType.USER_YAML})
                await async_load_platform(
                    hass,
                    Platform.SENSOR,
                    DOMAIN,
                    sensor_config,
                    reload_config,
                )

        # Reload all config entries
        for entry in hass.config_entries.async_entries(DOMAIN):
            _LOGGER.debug("Reloading config entry %s", entry.entry_id)
            await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD,
        _reload_config,
    )


def setup_standby_group(hass: HomeAssistant, domain_config: ConfigType) -> None:
    async def _create_standby_group(event: None) -> None:
        hass.async_create_task(
            async_load_platform(
                hass,
                SENSOR_DOMAIN,
                DOMAIN,
                {DISCOVERY_TYPE: PowercalcDiscoveryType.STANDBY_GROUP},
                domain_config,
            ),
        )

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STARTED,
        _create_standby_group,
    )


def setup_domain_groups(hass: HomeAssistant, global_config: ConfigType) -> None:
    domain_groups: list[str] | None = global_config.get(CONF_CREATE_DOMAIN_GROUPS)
    if not domain_groups:
        return

    _LOGGER.debug("Setting up domain based group sensors..")
    for domain in domain_groups:
        hass.async_create_task(
            async_load_platform(
                hass,
                SENSOR_DOMAIN,
                DOMAIN,
                {
                    DISCOVERY_TYPE: PowercalcDiscoveryType.DOMAIN_GROUP,
                    CONF_DOMAIN: domain,
                },
                global_config,
            ),
        )


async def setup_yaml_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    domain_config: ConfigType,
) -> None:
    sensors: list = domain_config.get(CONF_SENSORS, [])
    primary_sensors = []
    secondary_sensors = []

    for sensor_config in sensors:
        sensor_config.update({DISCOVERY_TYPE: PowercalcDiscoveryType.USER_YAML})

        if CONF_INCLUDE in sensor_config:
            secondary_sensors.append(sensor_config)
        else:
            primary_sensors.append(sensor_config)

    async def _load_secondary_sensors(_: None) -> None:
        """Load secondary sensors after primary sensors."""
        await asyncio.gather(
            *(
                hass.async_create_task(
                    async_load_platform(
                        hass,
                        Platform.SENSOR,
                        DOMAIN,
                        sensor_config,
                        config,
                    ),
                )
                for sensor_config in secondary_sensors
            ),
        )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _load_secondary_sensors)

    await asyncio.gather(
        *(
            hass.async_create_task(
                async_load_platform(
                    hass,
                    Platform.SENSOR,
                    DOMAIN,
                    sensor_config,
                    config,
                ),
            )
            for sensor_config in primary_sensors
        ),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Powercalc integration from a config entry."""

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_entry))

    # Check if this is the initial creation of the global configuration entry
    # If so, update the global configuration with the GUI configuration
    # When the flag is set, the global configuration has already been applied during async_setup
    if entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
        global_config = hass.data[DOMAIN][DOMAIN_CONFIG]
        if global_config.get(FLAG_HAS_GLOBAL_GUI_CONFIG, False) is False:
            await apply_global_gui_configuration_changes(hass, entry)

    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update a given config entry."""

    if entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
        await apply_global_gui_configuration_changes(hass, entry)

    await hass.config_entries.async_reload(entry.entry_id)

    # Also reload all "parent" groups referring this group as a subgroup
    for related_entry in get_entries_having_subgroup(hass, entry):
        await hass.config_entries.async_reload(related_entry.entry_id)


async def apply_global_gui_configuration_changes(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply global configuration changes to all entities."""
    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]
    global_config.update(get_global_gui_configuration(entry))
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
            continue
        if entry.state != ConfigEntryState.LOADED:  # pragma: no cover
            continue
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry,
        PLATFORMS,
    )

    if unload_ok:
        used_unique_ids: list[str] = hass.data[DOMAIN][DATA_USED_UNIQUE_IDS]
        try:
            if config_entry.unique_id:
                used_unique_ids.remove(config_entry.unique_id)
        except ValueError:
            return True

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Called after a config entry is removed."""
    discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]
    discovery_manager.remove_initialized_flow(config_entry)

    updated_entries: list[ConfigEntry] = []

    sensor_type = config_entry.data.get(CONF_SENSOR_TYPE)
    if sensor_type == SensorType.VIRTUAL_POWER:
        updated_entries = await remove_power_sensor_from_associated_groups(
            hass,
            config_entry,
        )
    if sensor_type == SensorType.GROUP:
        updated_entries = await remove_group_from_power_sensor_entry(hass, config_entry)

    for entry in updated_entries:
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    version = config_entry.version
    data = {**config_entry.data}

    if version <= 1:
        conf_fixed = data.get(CONF_FIXED, {})
        if CONF_POWER in conf_fixed and CONF_POWER_TEMPLATE in conf_fixed:
            conf_fixed.pop(CONF_POWER, None)

    if version <= 2 and data.get(CONF_SENSOR_TYPE) and CONF_CREATE_ENERGY_SENSOR not in data:
        data[CONF_CREATE_ENERGY_SENSOR] = True

    if version <= 3:
        conf_playbook = data.get(CONF_PLAYBOOK, {})
        if CONF_STATES_TRIGGER in conf_playbook:
            data[CONF_PLAYBOOK][CONF_STATE_TRIGGER] = conf_playbook.pop(CONF_STATES_TRIGGER)

    hass.config_entries.async_update_entry(config_entry, data=data, version=4)

    return True


async def repair_none_config_entries_issue(hass: HomeAssistant) -> None:
    """Repair issue with config entries having None as data."""
    entity_registry = er.async_get(hass)
    entries = [entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.title == "None"]
    for entry in entries:
        _LOGGER.debug("Removing entry %s with None data", entry.entry_id)
        entities = entity_registry.entities.get_entries_for_config_entry_id(entry.entry_id)
        for entity in entities:
            entity_registry.async_remove(entity.entity_id)
        try:
            unique_id = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"  # noqa: S311
            object.__setattr__(entry, "unique_id", unique_id)
            hass.config_entries._entries._index_entry(entry)  # noqa
            await hass.config_entries.async_remove(entry.entry_id)
        except Exception as e:  # noqa: BLE001  # pragma: no cover
            _LOGGER.error("problem while cleaning up None entities", exc_info=e)  # pragma: no cover


def _notify_message(
    hass: HomeAssistant,
    notification_id: str,
    title: str,
    message: str,
) -> None:  # pragma: no cover
    """Notify user with persistent notification."""
    hass.async_create_task(
        hass.services.async_call(
            domain="persistent_notification",
            service="create",
            service_data={
                "title": title,
                "message": message,
                "notification_id": f"{DOMAIN}.{notification_id}",
            },
        ),
    )
