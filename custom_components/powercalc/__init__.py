"""The PowerCalc integration."""

from __future__ import annotations

import logging
import re
from typing import Optional

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter import DEFAULT_OFFSET, max_28_days
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.config_entries import (
    SOURCE_INTEGRATION_DISCOVERY,
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery, discovery_flow
from homeassistant.helpers.typing import ConfigType

from .aliases import MANUFACTURER_WLED
from .common import SourceEntity, create_source_entity, validate_name_pattern
from .const import (
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
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
    CalculationStrategy,
    PowercalcDiscoveryType,
    SensorType,
    UnitPrefix,
)
from .errors import ModelNotSupported
from .power_profile.model_discovery import (
    PowerProfile,
    autodiscover_model,
    get_power_profile,
)
from .power_profile.power_profile import DEVICE_DOMAINS
from .sensors.group import (
    remove_group_from_power_sensor_entry,
    remove_power_sensor_from_associated_groups,
)
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
                    vol.Optional(
                        CONF_DISABLE_EXTENDED_ATTRIBUTES, default=False
                    ): cv.boolean,
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
                    vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): cv.boolean,
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
        CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
        CONF_IGNORE_UNAVAILABLE_STATE: False,
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

    if domain_config.get(CONF_ENABLE_AUTODISCOVERY):
        discovery_manager = DiscoveryManager(hass, config)
        await discovery_manager.start_discovery()

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
        used_unique_ids: list[str] = hass.data[DOMAIN][DATA_USED_UNIQUE_IDS]
        try:
            used_unique_ids.remove(config_entry.unique_id)
        except ValueError:
            return True

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Called after a config entry is removed."""
    updated_entries: list[ConfigEntry] = []

    sensor_type = config_entry.data.get(CONF_SENSOR_TYPE)
    if sensor_type == SensorType.VIRTUAL_POWER:
        updated_entries = await remove_power_sensor_from_associated_groups(
            hass, config_entry
        )
    if sensor_type == SensorType.GROUP:
        updated_entries = await remove_group_from_power_sensor_entry(hass, config_entry)

    for entry in updated_entries:
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_reload(entry.entry_id)


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


class DiscoveryManager:
    """
    This class is responsible for scanning the HA instance for entities and their manufacturer / model info
    It checks if any of these devices is supported in the powercalc library
    When entities are found it will dispatch a discovery flow, so the user can add them to their HA instance
    """

    def __init__(self, hass: HomeAssistant, ha_config: ConfigType):
        self.hass = hass
        self.ha_config = ha_config
        self.manually_configured_entities: list[str] | None = None

    async def start_discovery(self):
        """Start the discovery procedure"""

        _LOGGER.debug("Start auto discovering entities")
        entity_registry = er.async_get(self.hass)
        for entity_entry in list(entity_registry.entities.values()):
            if entity_entry.disabled:
                continue

            if entity_entry.domain not in DEVICE_DOMAINS.values():
                continue

            has_user_config = self._is_user_configured(entity_entry.entity_id)
            if has_user_config:
                _LOGGER.debug(
                    "%s: Entity is manually configured, skipping auto configuration",
                    entity_entry.entity_id,
                )
                continue

            model_info = await autodiscover_model(self.hass, entity_entry)
            if not model_info:
                continue

            source_entity = await create_source_entity(
                entity_entry.entity_id, self.hass
            )

            if (
                model_info.manufacturer == MANUFACTURER_WLED
                and entity_entry.domain == LIGHT_DOMAIN
                and not re.search(
                    "master|segment",
                    str(entity_entry.original_name),
                    flags=re.IGNORECASE,
                )
            ):
                self._init_entity_discovery(
                    source_entity,
                    power_profile=None,
                    extra_discovery_data={
                        CONF_MODE: CalculationStrategy.WLED,
                        CONF_MANUFACTURER: model_info.manufacturer,
                        CONF_MODEL: model_info.model,
                    },
                )
                continue

            try:
                power_profile = await get_power_profile(
                    self.hass, {}, model_info=model_info
                )
                if not power_profile:
                    continue
            except ModelNotSupported:
                _LOGGER.debug(
                    "%s: Model not found in library, skipping discovery",
                    entity_entry.entity_id,
                )
                continue

            if not power_profile.is_entity_domain_supported(source_entity.domain):
                continue

            self._init_entity_discovery(source_entity, power_profile, {})

        _LOGGER.debug("Done auto discovering entities")

    @callback
    def _init_entity_discovery(
        self,
        source_entity: SourceEntity,
        power_profile: PowerProfile | None,
        extra_discovery_data: Optional[dict],
    ):
        """Dispatch the discovery flow for a given entity"""
        existing_entries = [
            entry
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.unique_id == source_entity.unique_id
        ]
        if existing_entries:
            _LOGGER.debug(
                f"{source_entity.entity_id}: Already setup with discovery, skipping new discovery"
            )
            return

        discovery_data = {
            CONF_UNIQUE_ID: source_entity.unique_id,
            CONF_NAME: source_entity.name,
            CONF_ENTITY_ID: source_entity.entity_id,
            DISCOVERY_SOURCE_ENTITY: source_entity,
        }

        if power_profile:
            discovery_data[DISCOVERY_POWER_PROFILE] = power_profile
            discovery_data[CONF_MANUFACTURER] = power_profile.manufacturer
            discovery_data[CONF_MODEL] = power_profile.model

        if extra_discovery_data:
            discovery_data.update(extra_discovery_data)

        discovery_flow.async_create_flow(
            self.hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=discovery_data,
        )

        # Code below if for legacy discovery routine, will be removed somewhere in the future
        if power_profile and not power_profile.is_additional_configuration_required:
            discovery_info = {
                CONF_ENTITY_ID: source_entity.entity_id,
                DISCOVERY_SOURCE_ENTITY: source_entity,
                DISCOVERY_POWER_PROFILE: power_profile,
                DISCOVERY_TYPE: PowercalcDiscoveryType.LIBRARY,
            }
            self.hass.async_create_task(
                discovery.async_load_platform(
                    self.hass, SENSOR_DOMAIN, DOMAIN, discovery_info, self.ha_config
                )
            )

    def _is_user_configured(self, entity_id: str) -> bool:
        """
        Check if user have setup powercalc sensors for a given entity_id.
        Either with the YAML or GUI method.
        """
        if not self.manually_configured_entities:
            self.manually_configured_entities = (
                self._load_manually_configured_entities()
            )

        return entity_id in self.manually_configured_entities

    def _load_manually_configured_entities(self) -> list[str]:
        """Looks at the YAML and GUI config entries for all the configured entity_id's"""
        entities = []

        # Find entity ids in yaml config
        if SENSOR_DOMAIN in self.ha_config:
            sensor_config = self.ha_config.get(SENSOR_DOMAIN)
            platform_entries = [
                item
                for item in sensor_config
                if isinstance(item, dict) and item.get(CONF_PLATFORM) == DOMAIN
            ]
            for entry in platform_entries:
                entities.extend(self._find_entity_ids_in_yaml_config(entry))

        # Add entities from existing config entries
        entities.extend(
            [
                entry.data.get(CONF_ENTITY_ID)
                for entry in self.hass.config_entries.async_entries(DOMAIN)
                if entry.source == SOURCE_USER
            ]
        )

        return entities

    def _find_entity_ids_in_yaml_config(self, search_dict: dict):
        """
        Takes a dict with nested lists and dicts,
        and searches all dicts for a key of the field
        provided.
        """
        found_entity_ids = []

        for key, value in search_dict.items():

            if key == "entity_id":
                found_entity_ids.append(value)

            elif isinstance(value, dict):
                results = self._find_entity_ids_in_yaml_config(value)
                for result in results:
                    found_entity_ids.append(result)

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        results = self._find_entity_ids_in_yaml_config(item)
                        for result in results:
                            found_entity_ids.append(result)

        return found_entity_ids
