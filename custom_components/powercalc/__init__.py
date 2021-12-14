"""The PowerCalc integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter import DEFAULT_OFFSET, max_28_days
from homeassistant.components.utility_meter.const import (
    DAILY,
    METER_TYPES,
    MONTHLY,
    WEEKLY,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_SCAN_INTERVAL
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import HomeAssistantType

from .common import create_source_entity, validate_name_pattern
from .const import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TYPES,
    DATA_CALCULATOR_FACTORY,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERED_ENTITIES,
    DISCOVERY_LIGHT_MODEL,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DOMAIN_CONFIG,
)
from .errors import ModelNotSupported
from .model_discovery import get_light_model, is_supported_for_autodiscovery
from .strategy.factory import PowerCalculatorStrategyFactory

DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
DEFAULT_POWER_NAME_PATTERN = "{} power"
DEFAULT_ENERGY_NAME_PATTERN = "{} energy"

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
                        CONF_ENERGY_SENSOR_NAMING, default=DEFAULT_ENERGY_NAME_PATTERN
                    ): validate_name_pattern,
                    vol.Optional(CONF_ENABLE_AUTODISCOVERY, default=False): cv.boolean,
                    vol.Optional(CONF_CREATE_ENERGY_SENSORS, default=True): cv.boolean,
                    vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): cv.boolean,
                    vol.Optional(
                        CONF_UTILITY_METER_TYPES, default=[DAILY, WEEKLY, MONTHLY]
                    ): vol.All(cv.ensure_list, [vol.In(METER_TYPES)]),
                    vol.Optional(
                        CONF_UTILITY_METER_OFFSET, default=DEFAULT_OFFSET
                    ): vol.All(cv.time_period, cv.positive_timedelta, max_28_days),
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    domain_config = config.get(DOMAIN) or {
        CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
        CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_ENABLE_AUTODISCOVERY: True,
    }

    hass.data[DOMAIN] = {
        DATA_CALCULATOR_FACTORY: PowerCalculatorStrategyFactory(hass),
        DOMAIN_CONFIG: domain_config,
        DATA_CONFIGURED_ENTITIES: [],
        DATA_DISCOVERED_ENTITIES: [],
    }

    await autodiscover_entities(config, domain_config, hass)

    return True


async def autodiscover_entities(
    config: dict, domain_config: dict, hass: HomeAssistantType
):
    """Discover entities supported for powercalc autoconfiguration in HA instance"""

    if not domain_config.get(CONF_ENABLE_AUTODISCOVERY):
        return

    _LOGGER.debug("Start auto discovering entities")
    entity_registry = await er.async_get_registry(hass)
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
