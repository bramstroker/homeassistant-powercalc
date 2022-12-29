from __future__ import annotations

import logging

import re
from typing import Optional

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
import homeassistant.helpers.entity_registry as er

from homeassistant.config_entries import (
    SOURCE_INTEGRATION_DISCOVERY,
    SOURCE_USER,
)
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery, discovery_flow
from homeassistant.helpers.typing import ConfigType
from .aliases import MANUFACTURER_WLED
from .common import SourceEntity, create_source_entity
from .const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    DISCOVERY_POWER_PROFILE,
    DISCOVERY_SOURCE_ENTITY,
    DISCOVERY_TYPE,
    DOMAIN,
    CalculationStrategy,
    PowercalcDiscoveryType,
)
from .errors import ModelNotSupported
from .power_profile.model_discovery import (
    PowerProfile,
    autodiscover_model,
    get_power_profile,
)
from .power_profile.power_profile import DEVICE_DOMAINS

_LOGGER = logging.getLogger(__name__)


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

    async def start_discovery(self) -> None:
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
    ) -> None:
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