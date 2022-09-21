"""The PowerCalc integration."""

from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.utility_meter import DEFAULT_OFFSET, max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .common import create_source_entity, validate_name_pattern
from .const import (
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DATA_CALCULATOR_FACTORY,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERED_ENTITIES,
    DATA_DOMAIN_ENTITIES,
    DATA_USED_UNIQUE_IDS,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENTITY_CATEGORY,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_POWER_SENSOR_PRECISION,
    DEFAULT_UPDATE_FREQUENCY,
    DEFAULT_UTILITY_METER_TYPES,
    DISCOVERY_POWER_PROFILE,
    DISCOVERY_SOURCE_ENTITY,
    DISCOVERY_TYPE,
    DOMAIN,
    DOMAIN_CONFIG,
    ENERGY_INTEGRATION_METHODS,
    ENTITY_CATEGORIES,
    MIN_HA_VERSION,
    PowercalcDiscoveryType,
    UnitPrefix,
)
from .errors import ModelNotSupported
from .power_profile.model_discovery import (
    get_power_profile,
    has_manufacturer_and_model_information,
)
from .sensors.group import update_associated_group_entry
from .strategy.factory import PowerCalculatorStrategyFactory

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.deprecated(
                CONF_SCAN_INTERVAL, replacement_key=CONF_FORCE_UPDATE_FREQUENCY
            ),
            vol.Schema(
                {
                    vol.Optional(
                        CONF_FORCE_UPDATE_FREQUENCY, default=DEFAULT_UPDATE_FREQUENCY
                    ): cv.time_period,
                    vol.Optional(
                        CONF_POWER_SENSOR_NAMING, default=DEFAULT_POWER_NAME_PATTERN
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_POWER_SENSOR_FRIENDLY_NAMING
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_POWER_SENSOR_CATEGORY, default=DEFAULT_ENTITY_CATEGORY
                    ): vol.In(ENTITY_CATEGORIES),
                    vol.Optional(
                        CONF_ENERGY_SENSOR_NAMING, default=DEFAULT_ENERGY_NAME_PATTERN
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_ENERGY_SENSOR_FRIENDLY_NAMING
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_ENERGY_SENSOR_CATEGORY, default=DEFAULT_ENTITY_CATEGORY
                    ): vol.In(ENTITY_CATEGORIES),
                    vol.Optional(CONF_ENABLE_AUTODISCOVERY, default=True): cv.boolean,
                    vol.Optional(CONF_CREATE_ENERGY_SENSORS, default=True): cv.boolean,
                    vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): cv.boolean,
                    vol.Optional(CONF_UTILITY_METER_TARIFFS, default=[]): vol.All(
                        cv.ensure_list, [cv.string]
                    ),
                    vol.Optional(
                        CONF_UTILITY_METER_TYPES, default=DEFAULT_UTILITY_METER_TYPES
                    ): vol.All(cv.ensure_list, [vol.In(METER_TYPES)]),
                    vol.Optional(
                        CONF_UTILITY_METER_OFFSET, default=DEFAULT_OFFSET
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
                        CONF_ENERGY_SENSOR_UNIT_PREFIX, default=UnitPrefix.KILO
                    ): vol.In([cls.value for cls in UnitPrefix]),
                    vol.Optional(CONF_CREATE_DOMAIN_GROUPS, default=[]): vol.All(
                        cv.ensure_list, [cv.string]
                    ),
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):
        _LOGGER.critical(
            "Your HA version is outdated for this version of powercalc. Minimum required HA version is %s",
            MIN_HA_VERSION,
        )
        return False

    domain_config = config.get(DOMAIN) or {
        CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
        CONF_POWER_SENSOR_PRECISION: DEFAULT_POWER_SENSOR_PRECISION,
        CONF_POWER_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
        CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
        CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
        CONF_ENERGY_SENSOR_PRECISION: DEFAULT_ENERGY_SENSOR_PRECISION,
        CONF_ENERGY_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
        CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
        CONF_FORCE_UPDATE_FREQUENCY: DEFAULT_UPDATE_FREQUENCY,
        CONF_CREATE_DOMAIN_GROUPS: [],
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_ENABLE_AUTODISCOVERY: True,
        CONF_UTILITY_METER_OFFSET: DEFAULT_OFFSET,
        CONF_UTILITY_METER_TYPES: DEFAULT_UTILITY_METER_TYPES,
    }

    hass.data[DOMAIN] = {
        DATA_CALCULATOR_FACTORY: PowerCalculatorStrategyFactory(hass),
        DOMAIN_CONFIG: domain_config,
        DATA_CONFIGURED_ENTITIES: {},
        DATA_DOMAIN_ENTITIES: {},
        DATA_DISCOVERED_ENTITIES: {},
        DATA_USED_UNIQUE_IDS: [],
    }

    await autodiscover_entities(config, domain_config, hass)

    if domain_config.get(CONF_CREATE_DOMAIN_GROUPS):

        async def _create_domain_groups(event: None):
            await create_domain_groups(
                hass,
                domain_config,
                domain_config.get(CONF_CREATE_DOMAIN_GROUPS),
            )

        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            _create_domain_groups,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Powercalc integration from a config entry."""

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update a given config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    if unload_ok:
        updated_group_entry = await update_associated_group_entry(
            hass, config_entry, remove=True
        )
        if updated_group_entry:
            await hass.config_entries.async_reload(updated_group_entry.entry_id)

        used_unique_ids: list[str] = hass.data[DOMAIN][DATA_USED_UNIQUE_IDS]
        try:
            used_unique_ids.remove(config_entry.unique_id)
        except ValueError:
            return True

    return unload_ok


async def autodiscover_entities(config: dict, domain_config: dict, hass: HomeAssistant):
    """Discover entities supported for powercalc autoconfiguration in HA instance"""

    if not domain_config.get(CONF_ENABLE_AUTODISCOVERY):
        return

    _LOGGER.debug("Start auto discovering entities")
    entity_registry = er.async_get(hass)
    for entity_entry in list(entity_registry.entities.values()):
        if entity_entry.disabled:
            continue

        if entity_entry.domain not in (LIGHT_DOMAIN, SWITCH_DOMAIN):
            continue

        if not await has_manufacturer_and_model_information(hass, entity_entry):
            continue

        source_entity = await create_source_entity(entity_entry.entity_id, hass)
        try:
            power_profile = await get_power_profile(
                hass, {}, source_entity.entity_entry
            )
            if not power_profile:
                continue
        except ModelNotSupported:
            _LOGGER.debug(
                "%s: Model not found in library, skipping auto configuration",
                entity_entry.entity_id,
            )
            continue

        has_user_config = is_user_configured(hass, config, entity_entry.entity_id)

        if power_profile.is_additional_configuration_required and not has_user_config:
            _LOGGER.warning(
                f"{entity_entry.entity_id}: Model found in database, but needs additional manual configuration to be loaded"
            )
            continue

        if has_user_config:
            _LOGGER.debug(
                "%s: Entity is manually configured, skipping auto configuration",
                entity_entry.entity_id,
            )
            continue

        if not power_profile.is_entity_domain_supported(source_entity.domain):
            continue

        discovery_info = {
            CONF_ENTITY_ID: entity_entry.entity_id,
            DISCOVERY_SOURCE_ENTITY: source_entity,
            DISCOVERY_POWER_PROFILE: power_profile,
            DISCOVERY_TYPE: PowercalcDiscoveryType.LIBRARY,
        }
        hass.async_create_task(
            discovery.async_load_platform(
                hass, SENSOR_DOMAIN, DOMAIN, discovery_info, config
            )
        )

    _LOGGER.debug("Done auto discovering entities")


def is_user_configured(hass: HomeAssistant, config: dict, entity_id: str) -> bool:
    """
    Check if user have setup powercalc sensors for a given entity_id.
    Either with the YAML or GUI method.
    """
    if SENSOR_DOMAIN in config:
        sensor_config = config.get(SENSOR_DOMAIN)
        for item in sensor_config:
            if (
                isinstance(item, dict)
                and item.get(CONF_PLATFORM) == DOMAIN
                and item.get(CONF_ENTITY_ID) == entity_id
            ):
                return True

    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if config_entry.data.get(CONF_ENTITY_ID) == entity_id:
            return True

    return False


async def create_domain_groups(
    hass: HomeAssistant, global_config: dict, domains: list[str]
):
    """Create group sensors aggregating all power sensors from given domains"""
    _LOGGER.debug("Setting up domain based group sensors..")
    for domain in domains:
        if domain not in hass.data[DOMAIN].get(DATA_DOMAIN_ENTITIES):
            _LOGGER.error(f"Cannot setup group for domain {domain}, no entities found")
            continue

        domain_entities = hass.data[DOMAIN].get(DATA_DOMAIN_ENTITIES)[domain]

        hass.async_create_task(
            discovery.async_load_platform(
                hass,
                SENSOR_DOMAIN,
                DOMAIN,
                {
                    DISCOVERY_TYPE: PowercalcDiscoveryType.DOMAIN_GROUP,
                    CONF_ENTITIES: domain_entities,
                    CONF_DOMAIN: domain,
                },
                global_config,
            )
        )
