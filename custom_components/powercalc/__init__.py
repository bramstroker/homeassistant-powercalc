"""The PowerCalc integration."""

from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter import DEFAULT_OFFSET, max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import HomeAssistantType

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
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENTITY_CATEGORY,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_POWER_SENSOR_PRECISION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UTILITY_METER_TYPES,
    DISCOVERY_LIGHT_MODEL,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DOMAIN_CONFIG,
    ENERGY_INTEGRATION_METHODS,
    ENTITY_CATEGORIES,
    MIN_HA_VERSION,
)
from .errors import ModelNotSupported
from .model_discovery import get_light_model, is_supported_for_autodiscovery
from .sensors.group import create_group_sensors
from .strategy.factory import PowerCalculatorStrategyFactory

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
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


async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
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
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
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
        DATA_DISCOVERED_ENTITIES: [],
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


async def autodiscover_entities(
    config: dict, domain_config: dict, hass: HomeAssistantType
):
    """Discover entities supported for powercalc autoconfiguration in HA instance"""

    if not domain_config.get(CONF_ENABLE_AUTODISCOVERY):
        return

    _LOGGER.debug("Start auto discovering entities")
    entity_registry = er.async_get(hass)
    for entity_entry in list(entity_registry.entities.values()):
        if entity_entry.disabled:
            continue

        if entity_entry.domain != LIGHT_DOMAIN:
            continue

        if not await is_supported_for_autodiscovery(hass, entity_entry):
            continue

        source_entity = await create_source_entity(entity_entry.entity_id, hass)
        try:
            light_model = await get_light_model(hass, {}, source_entity.entity_entry)
            if not light_model.is_autodiscovery_allowed:
                _LOGGER.debug(
                    f"{entity_entry.entity_id}: Model found in database, but needs manual configuration"
                )
                continue
        except ModelNotSupported:
            _LOGGER.debug(
                "%s: Model not found in library, skipping auto configuration",
                entity_entry.entity_id,
            )
            continue

        if not light_model:
            continue

        discovery_info = {
            CONF_ENTITY_ID: entity_entry.entity_id,
            DISCOVERY_SOURCE_ENTITY: source_entity,
            DISCOVERY_LIGHT_MODEL: light_model,
        }
        hass.async_create_task(
            discovery.async_load_platform(
                hass, SENSOR_DOMAIN, DOMAIN, discovery_info, config
            )
        )

    _LOGGER.debug("Done auto discovering entities")


async def create_domain_groups(
    hass: HomeAssistantType, global_config: dict, domains: list[str]
):
    """Create group sensors aggregating all power sensors from given domains"""
    sensor_component = hass.data[SENSOR_DOMAIN]
    sensor_config = global_config.copy()
    _LOGGER.debug(f"Setting up domain based group sensors..")
    for domain in domains:
        if not domain in hass.data[DOMAIN].get(DATA_DOMAIN_ENTITIES):
            _LOGGER.error(f"Cannot setup group for domain {domain}, no entities found")
            continue

        domain_entities = hass.data[DOMAIN].get(DATA_DOMAIN_ENTITIES)[domain]
        sensor_config[CONF_UNIQUE_ID] = f"powercalc_domaingroup_{domain}"
        group_name = f"All {domain}"

        entities = await create_group_sensors(
            group_name, sensor_config, domain_entities, hass
        )
        await sensor_component.async_add_entities(entities)
    return []
