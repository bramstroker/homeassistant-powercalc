"""The PowerCalc integration."""

from __future__ import annotations

import asyncio
from functools import partial
import logging
import random
import time
from typing import Any

from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter import max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENABLED,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
    __version__ as HA_VERSION,  # noqa: N812
)
from homeassistant.core import Event, HassJob, HomeAssistant, ServiceCall, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity_platform import async_get_platforms
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .analytics.analytics import ANALYTICS_INTERVAL, Analytics
from .common import validate_name_pattern
from .configuration.global_config import FLAG_HAS_GLOBAL_GUI_CONFIG, get_global_configuration, get_global_gui_configuration
from .const import (
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_STANDBY_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_LIBRARY_DOWNLOAD,
    CONF_DISCOVERY,
    CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED,
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
    CONF_ENABLE_ANALYTICS,
    CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_EXCLUDE_DEVICE_TYPES,
    CONF_EXCLUDE_SELF_USAGE,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_POWER_UPDATE_INTERVAL,
    CONF_GROUP_UPDATE_INTERVAL_DEPRECATED,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
    CONF_SENSORS,
    CONF_UNAVAILABLE_POWER,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DATA_ANALYTICS,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERY_MANAGER,
    DATA_DOMAIN_ENTITIES,
    DATA_ENTITIES,
    DATA_GROUP_ENTITIES,
    DATA_STANDBY_POWER_SENSORS,
    DATA_USED_UNIQUE_IDS,
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
from .discovery import DiscoveryManager, DiscoveryStatus
from .migrate import async_migrate_config_entry
from .power_profile.power_profile import DeviceType
from .sensor import SENSOR_CONFIG
from .sensors.group.config_entry_utils import (
    get_entries_excluding_global_config,
    get_entries_having_subgroup,
    remove_group_from_power_sensor_entry,
    remove_power_sensor_from_associated_groups,
)
from .service.gui_configuration import SERVICE_SCHEMA, change_gui_configuration

PLATFORMS = [Platform.SENSOR, Platform.SELECT]

DISCOVERY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENABLED): cv.boolean,
        vol.Optional(CONF_EXCLUDE_DEVICE_TYPES): vol.All(
            cv.ensure_list,
            [cls.value for cls in DeviceType],
        ),
        vol.Optional(CONF_EXCLUDE_SELF_USAGE): cv.boolean,
    },
)
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN, default=dict): vol.All(
            cv.deprecated(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED),
            cv.deprecated(CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED),
            cv.deprecated(CONF_ENABLE_AUTODISCOVERY_DEPRECATED),
            cv.deprecated(CONF_GROUP_UPDATE_INTERVAL_DEPRECATED),
            cv.deprecated(CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED),
            vol.Schema(
                {
                    vol.Optional(CONF_ENABLE_ANALYTICS): cv.boolean,
                    vol.Optional(
                        CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
                    ): cv.time_period,
                    vol.Optional(CONF_GROUP_UPDATE_INTERVAL_DEPRECATED): cv.positive_int,
                    vol.Optional(CONF_GROUP_POWER_UPDATE_INTERVAL): cv.positive_int,
                    vol.Optional(CONF_GROUP_ENERGY_UPDATE_INTERVAL): cv.positive_int,
                    vol.Optional(CONF_ENERGY_UPDATE_INTERVAL): cv.positive_int,
                    vol.Optional(CONF_POWER_SENSOR_NAMING): validate_name_pattern,
                    vol.Optional(CONF_POWER_SENSOR_FRIENDLY_NAMING): validate_name_pattern,
                    vol.Optional(CONF_POWER_SENSOR_CATEGORY): vol.In(ENTITY_CATEGORIES),
                    vol.Optional(CONF_ENERGY_SENSOR_NAMING): validate_name_pattern,
                    vol.Optional(CONF_ENERGY_SENSOR_FRIENDLY_NAMING): validate_name_pattern,
                    vol.Optional(CONF_ENERGY_SENSOR_CATEGORY): vol.In(ENTITY_CATEGORIES),
                    vol.Optional(CONF_DISABLE_EXTENDED_ATTRIBUTES): cv.boolean,
                    vol.Optional(CONF_DISABLE_LIBRARY_DOWNLOAD): cv.boolean,
                    vol.Optional(CONF_DISCOVERY): DISCOVERY_SCHEMA,
                    vol.Optional(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED): vol.All(
                        cv.ensure_list,
                        [cls.value for cls in DeviceType],
                    ),
                    vol.Optional(CONF_ENABLE_AUTODISCOVERY_DEPRECATED): cv.boolean,
                    vol.Optional(CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED): cv.boolean,
                    vol.Optional(CONF_CREATE_ENERGY_SENSORS): cv.boolean,
                    vol.Optional(CONF_CREATE_UTILITY_METERS): cv.boolean,
                    vol.Optional(CONF_UTILITY_METER_TARIFFS): vol.All(cv.ensure_list, [cv.string]),
                    vol.Optional(CONF_UTILITY_METER_TYPES): vol.All(cv.ensure_list, [vol.In(METER_TYPES)]),
                    vol.Optional(
                        CONF_UTILITY_METER_OFFSET,
                    ): vol.All(cv.time_period, cv.positive_timedelta, max_28_days),
                    vol.Optional(CONF_ENERGY_INTEGRATION_METHOD): vol.In(ENERGY_INTEGRATION_METHODS),
                    vol.Optional(CONF_ENERGY_SENSOR_PRECISION): cv.positive_int,
                    vol.Optional(CONF_POWER_SENSOR_PRECISION): cv.positive_int,
                    vol.Optional(CONF_ENERGY_SENSOR_UNIT_PREFIX): vol.In([cls.value for cls in UnitPrefix]),
                    vol.Optional(CONF_CREATE_DOMAIN_GROUPS): vol.All(cv.ensure_list, [cv.string]),
                    vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): cv.boolean,
                    vol.Optional(CONF_UNAVAILABLE_POWER): vol.Coerce(float),
                    vol.Optional(CONF_SENSORS): vol.All(cv.ensure_list, [SENSOR_CONFIG]),
                    vol.Optional(CONF_INCLUDE_NON_POWERCALC_SENSORS): cv.boolean,
                    vol.Optional(CONF_CREATE_STANDBY_GROUP): cv.boolean,
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

    global_config = await get_global_configuration(hass, config)

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
        DATA_ANALYTICS: {},
    }

    await register_services(hass)

    await async_load_platform(hass, Platform.SELECT, DOMAIN, {}, config)
    await setup_yaml_sensors(hass, config, global_config)

    setup_domain_groups(hass, global_config)
    setup_standby_group(hass, global_config)

    try:
        await repair_none_config_entries_issue(hass)
    except Exception as e:  # noqa: BLE001  # pragma: no cover
        _LOGGER.error("problem while cleaning up None entities", exc_info=e)  # pragma: no cover

    await init_analytics(hass)

    return True


async def init_analytics(hass: HomeAssistant) -> None:
    """Initialize the Analytics manager and schedule daily submission"""
    analytics = Analytics(hass)
    await analytics.load()

    @callback
    def start_schedule(_event: Event) -> None:
        """Start the send schedule after the started event."""
        async_call_later(
            hass,
            900,
            HassJob(
                analytics.send_analytics,
                name="powercalc analytics startup",
                cancel_on_shutdown=True,
            ),
        )

        async_track_time_interval(
            hass,
            analytics.send_analytics,
            ANALYTICS_INTERVAL,
            name="powercalc analytics daily",
            cancel_on_shutdown=True,
        )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_schedule)


async def create_discovery_manager_instance(
    hass: HomeAssistant,
    ha_config: ConfigType,
    global_powercalc_config: ConfigType,
) -> DiscoveryManager:
    discovery_config = global_powercalc_config.get(CONF_DISCOVERY, {})
    exclude_device_types = [DeviceType(device_type) for device_type in discovery_config.get(CONF_EXCLUDE_DEVICE_TYPES, [])]
    exclude_self_usage = discovery_config.get(CONF_EXCLUDE_SELF_USAGE, False)
    enable_autodiscovery = discovery_config.get(CONF_ENABLED, True)

    manager = DiscoveryManager(
        hass,
        ha_config,
        exclude_device_types=exclude_device_types,
        exclude_self_usage_profiles=exclude_self_usage,
        enabled=enable_autodiscovery,
    )
    await manager.setup()
    return manager


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
            return  # pragma: nocover

        hass.data[DOMAIN][DATA_USED_UNIQUE_IDS] = []
        hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES] = {}
        hass.data[DOMAIN][DATA_ANALYTICS] = {}
        hass.data[DOMAIN][DOMAIN_CONFIG] = await get_global_configuration(hass, reload_config)

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

        global_config = await get_global_configuration(hass, reload_config)
        setup_domain_groups(hass, global_config)
        await create_standby_group(hass, global_config)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD,
        _reload_config,
    )


async def create_standby_group(
    hass: HomeAssistant,
    domain_config: ConfigType,
    event: Event[Any] | None = None,
) -> None:
    if not bool(domain_config.get(CONF_CREATE_STANDBY_GROUP, True)):
        return
    hass.async_create_task(
        async_load_platform(
            hass,
            SENSOR_DOMAIN,
            DOMAIN,
            {DISCOVERY_TYPE: PowercalcDiscoveryType.STANDBY_GROUP},
            domain_config,
        ),
    )


def setup_standby_group(hass: HomeAssistant, domain_config: ConfigType) -> None:
    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STARTED,
        partial(create_standby_group, hass, domain_config),
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

    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.SELECT])
    # await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    entry.async_on_unload(entry.add_update_listener(async_update_entry))

    # Check if this is the initial creation of the global configuration entry
    # If so, update the global configuration with the GUI configuration
    # When the flag is set, the global configuration has already been applied during async_setup
    if entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
        global_config = hass.data[DOMAIN][DOMAIN_CONFIG]
        if global_config.get(FLAG_HAS_GLOBAL_GUI_CONFIG, False) is False:
            await apply_global_gui_configuration_changes(hass, entry)

        discovery_enabled = bool(entry.data.get(CONF_DISCOVERY, {}).get(CONF_ENABLED, False))
        discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]
        if discovery_enabled and discovery_manager.status == DiscoveryStatus.DISABLED:
            _LOGGER.debug("Enabling discovery manager based on global configuration")
            discovery_manager.enable()
            await discovery_manager.setup()
        if not discovery_enabled and discovery_manager.status != DiscoveryStatus.DISABLED:
            _LOGGER.debug("Disabling discovery manager based on global configuration")
            await discovery_manager.disable()

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
    for entry in get_entries_excluding_global_config(hass):
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
    await async_migrate_config_entry(hass, config_entry)
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
