from __future__ import annotations

import logging
import re
from typing import Any

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER
from homeassistant.const import CONF_ENTITY_ID, CONF_PLATFORM
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.typing import ConfigType

from .common import SourceEntity, create_source_entity
from .const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSORS,
    DATA_DISCOVERY_MANAGER,
    DISCOVERY_POWER_PROFILE,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    CalculationStrategy,
)
from .errors import ModelNotSupportedError
from .helpers import get_or_create_unique_id
from .power_profile.factory import get_power_profile
from .power_profile.library import ModelInfo
from .power_profile.power_profile import DOMAIN_DEVICE_TYPE, DeviceType, PowerProfile

_LOGGER = logging.getLogger(__name__)

MANUFACTURER_WLED = "WLED"


async def get_power_profile_by_source_entity(hass: HomeAssistant, source_entity: SourceEntity) -> PowerProfile | None:
    """Given a certain entity, lookup the manufacturer and model and return the power profile."""
    try:
        discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]
    except KeyError:
        discovery_manager = DiscoveryManager(hass, {})
    return await get_power_profile(hass, {}, await discovery_manager.autodiscover_model(source_entity.entity_entry))


class DiscoveryManager:
    """This class is responsible for scanning the HA instance for entities and their manufacturer / model info
    It checks if any of these devices is supported in the powercalc library
    When entities are found it will dispatch a discovery flow, so the user can add them to their HA instance.
    """

    def __init__(self, hass: HomeAssistant, ha_config: ConfigType) -> None:
        self.hass = hass
        self.ha_config = ha_config
        self.power_profiles: dict[str, PowerProfile | None] = {}
        self.manually_configured_entities: list[str] | None = None
        self.initialized_flows: set[str] = set()

    async def start_discovery(self) -> None:
        """Start the discovery procedure."""

        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in existing_entries:
            if entry.unique_id:
                self.initialized_flows.add(entry.unique_id)

        _LOGGER.debug("Start auto discovering entities")
        entity_registry = er.async_get(self.hass)
        for entity_entry in list(entity_registry.entities.values()):
            model_info = await self.autodiscover_model(entity_entry)
            if not model_info:
                continue
            power_profile = await self.get_power_profile(
                entity_entry.entity_id,
                model_info,
            )
            source_entity = await create_source_entity(
                entity_entry.entity_id,
                self.hass,
            )
            if not await self.is_entity_supported(entity_entry):
                continue

            self._init_entity_discovery(source_entity, power_profile, {})

        _LOGGER.debug("Done auto discovering entities")

    async def get_power_profile(
        self,
        entity_id: str,
        model_info: ModelInfo,
    ) -> PowerProfile | None:
        if entity_id in self.power_profiles:
            return self.power_profiles[entity_id]

        try:
            self.power_profiles[entity_id] = await get_power_profile(
                self.hass,
                {},
                model_info=model_info,
            )
            return self.power_profiles[entity_id]
        except ModelNotSupportedError:
            _LOGGER.debug(
                "%s: Model not found in library, skipping discovery",
                entity_id,
            )
            return None

    async def is_entity_supported(self, entity_entry: er.RegistryEntry) -> bool:
        if not self.should_process_entity(entity_entry):
            return False

        model_info = await self.autodiscover_model(entity_entry)
        if not model_info or not model_info.manufacturer or not model_info.model:
            return False

        source_entity = await create_source_entity(
            entity_entry.entity_id,
            self.hass,
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
            return False

        power_profile = await self.get_power_profile(entity_entry.entity_id, model_info)
        if not power_profile:
            return False

        return power_profile.is_entity_domain_supported(source_entity)

    def should_process_entity(self, entity_entry: er.RegistryEntry) -> bool:
        """Do some validations on the registry entry to see if it qualifies for discovery."""
        if entity_entry.disabled:
            return False

        if entity_entry.domain not in DOMAIN_DEVICE_TYPE:
            return False

        if DOMAIN_DEVICE_TYPE[entity_entry.domain] == DeviceType.PRINTER and entity_entry.unit_of_measurement:
            return False

        if entity_entry.entity_category in [
            EntityCategory.CONFIG,
            EntityCategory.DIAGNOSTIC,
        ]:
            return False

        has_user_config = self._is_user_configured(entity_entry.entity_id)
        if has_user_config:
            _LOGGER.debug(
                "%s: Entity is manually configured, skipping auto configuration",
                entity_entry.entity_id,
            )
            return False

        return True

    async def autodiscover_model(self, entity_entry: er.RegistryEntry | None) -> ModelInfo | None:
        """Try to auto discover manufacturer and model from the known device information."""
        if not entity_entry or not entity_entry.device_id:
            return None

        model_info = await self.get_model_information(entity_entry)
        if not model_info:
            _LOGGER.debug(
                "%s: Cannot autodiscover model, manufacturer or model unknown from device registry",
                entity_entry.entity_id,
            )
            return None

        # Make sure we don't have a literal / in model_id,
        # so we don't get issues with sublut directory matching down the road
        # See github #658
        if "/" in model_info.model:
            model_info = ModelInfo(
                model_info.manufacturer,
                model_info.model.replace("/", "#slash#"),
                model_info.model_id,
            )

        _LOGGER.debug(
            "%s: Auto discovered model (manufacturer=%s, model=%s, model_id=%s)",
            entity_entry.entity_id,
            model_info.manufacturer,
            model_info.model,
            model_info.model_id,
        )
        return model_info

    async def get_model_information(self, entity_entry: er.RegistryEntry) -> ModelInfo | None:
        """See if we have enough information in device registry to automatically setup the power sensor."""
        if entity_entry.device_id is None:
            return None
        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get(entity_entry.device_id)
        if device_entry is None or device_entry.manufacturer is None or device_entry.model is None:
            return None

        manufacturer = str(device_entry.manufacturer)
        model = str(device_entry.model)
        model_id = device_entry.model_id if hasattr(device_entry, "model_id") else None

        if len(manufacturer) == 0 or len(model) == 0:
            return None

        return ModelInfo(manufacturer, model, model_id)

    @callback
    def _init_entity_discovery(
        self,
        source_entity: SourceEntity,
        power_profile: PowerProfile | None,
        extra_discovery_data: dict | None,
    ) -> None:
        """Dispatch the discovery flow for a given entity."""

        unique_id = get_or_create_unique_id({}, source_entity, power_profile)
        unique_ids_to_check = [unique_id]
        if unique_id.startswith("pc_"):
            unique_ids_to_check.append(unique_id[3:])

        if any(unique_id in self.initialized_flows for unique_id in unique_ids_to_check):
            _LOGGER.debug(
                "%s: Already setup with discovery, skipping new discovery",
                source_entity.entity_id,
            )
            return

        discovery_data: dict[str, Any] = {
            CONF_ENTITY_ID: source_entity.entity_id,
            DISCOVERY_SOURCE_ENTITY: source_entity,
        }

        if power_profile:
            discovery_data[DISCOVERY_POWER_PROFILE] = power_profile
            discovery_data[CONF_MANUFACTURER] = power_profile.manufacturer
            discovery_data[CONF_MODEL] = power_profile.model

        if extra_discovery_data:
            discovery_data.update(extra_discovery_data)

        self.initialized_flows.add(unique_id)
        discovery_flow.async_create_flow(
            self.hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=discovery_data,
        )

    def _is_user_configured(self, entity_id: str) -> bool:
        """Check if user have setup powercalc sensors for a given entity_id.
        Either with the YAML or GUI method.
        """
        if not self.manually_configured_entities:
            self.manually_configured_entities = self._load_manually_configured_entities()

        return entity_id in self.manually_configured_entities

    def _load_manually_configured_entities(self) -> list[str]:
        """Looks at the YAML and GUI config entries for all the configured entity_id's."""
        entities = []

        # Find entity ids in yaml config (Legacy)
        if SENSOR_DOMAIN in self.ha_config:  # pragma: no cover
            sensor_config = self.ha_config.get(SENSOR_DOMAIN)
            platform_entries = [item for item in sensor_config or {} if isinstance(item, dict) and item.get(CONF_PLATFORM) == DOMAIN]
            for entry in platform_entries:
                entities.extend(self._find_entity_ids_in_yaml_config(entry))

        # Find entity ids in yaml config (New)
        domain_config: ConfigType = self.ha_config.get(DOMAIN, {})
        if CONF_SENSORS in domain_config:
            sensors = domain_config[CONF_SENSORS]
            for sensor_config in sensors:
                entities.extend(self._find_entity_ids_in_yaml_config(sensor_config))

        # Add entities from existing config entries
        entities.extend(
            [str(entry.data.get(CONF_ENTITY_ID)) for entry in self.hass.config_entries.async_entries(DOMAIN) if entry.source == SOURCE_USER],
        )

        return entities

    def _find_entity_ids_in_yaml_config(self, search_dict: dict) -> list[str]:
        """Takes a dict with nested lists and dicts,
        and searches all dicts for a key of the field
        provided.
        """
        found_entity_ids: list[str] = []
        self._extract_entity_ids(search_dict, found_entity_ids)
        return found_entity_ids

    def _extract_entity_ids(self, search_dict: dict, found_entity_ids: list[str]) -> None:
        """Helper function to recursively extract entity IDs."""
        for key, value in search_dict.items():
            if key == CONF_ENTITY_ID:
                found_entity_ids.append(value)
            elif isinstance(value, dict):
                self._extract_entity_ids(value, found_entity_ids)
            elif isinstance(value, list):
                self._process_list_items(value, found_entity_ids)

    def _process_list_items(self, items: list, found_entity_ids: list[str]) -> None:
        """Helper function to process list items."""
        for item in items:
            if isinstance(item, dict):
                self._extract_entity_ids(item, found_entity_ids)
