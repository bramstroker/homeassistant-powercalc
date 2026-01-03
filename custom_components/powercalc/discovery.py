from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from enum import StrEnum
import logging
import re
from typing import Any

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER, ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_PLATFORM, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity import EntityCategory
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .common import SourceEntity, create_source_entity
from .const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSORS,
    DATA_DISCOVERY_MANAGER,
    DISCOVERY_POWER_PROFILES,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DUMMY_ENTITY_ID,
    MANUFACTURER_WLED,
    CalculationStrategy,
)
from .group_include.filter import CategoryFilter, CompositeFilter, DomainFilter, FilterOperator, LambdaFilter, NotFilter, get_filtered_entity_list
from .helpers import get_or_create_unique_id
from .power_profile.factory import get_power_profile
from .power_profile.library import ModelInfo, ProfileLibrary
from .power_profile.power_profile import SUPPORTED_DOMAINS, DeviceType, DiscoveryBy, PowerProfile

_LOGGER = logging.getLogger(__name__)


async def get_power_profile_by_source_entity(hass: HomeAssistant, source_entity: SourceEntity) -> PowerProfile | None:
    """Given a certain entity, lookup the manufacturer and model and return the power profile."""
    try:
        discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]
    except KeyError:
        discovery_manager = DiscoveryManager(hass, {})
    model_info = await discovery_manager.extract_model_info_from_device_info(source_entity.entity_entry)
    if not model_info:
        return None
    profiles = await discovery_manager.find_power_profiles(model_info, source_entity, DiscoveryBy.ENTITY)
    return profiles[0] if profiles else None


class DiscoveryStatus(StrEnum):
    DISABLED = "disabled"
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class DiscoveryManager:
    """This class is responsible for scanning the HA instance for entities and their manufacturer / model info
    It checks if any of these devices is supported in the powercalc library
    When entities are found it will dispatch a discovery flow, so the user can add them to their HA instance.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        ha_config: ConfigType,
        exclude_device_types: list[DeviceType] | None = None,
        exclude_self_usage_profiles: bool = False,
        enabled: bool = True,
    ) -> None:
        self.hass = hass
        self.ha_config = ha_config
        self.power_profiles: dict[str, PowerProfile | None] = {}
        self.manually_configured_entities: list[str] | None = None
        self.initialized_flows: set[str] = set()
        self.library: ProfileLibrary | None = None
        self._exclude_device_types = exclude_device_types or []
        self._exclude_self_usage_profiles = exclude_self_usage_profiles or False
        self._status = DiscoveryStatus.NOT_STARTED if enabled else DiscoveryStatus.DISABLED

    async def setup(self) -> None:
        """Setup the discovery manager. Start initial discovery and setup interval based rediscovery."""
        if self._status == DiscoveryStatus.DISABLED:
            _LOGGER.debug("Discovery manager is disabled, skipping setup")
            return

        await self.start_discovery()

        async def _rediscover(_: Any) -> None:  # noqa: ANN401
            """Rediscover entities."""
            await self.update_library_and_rediscover()

        async_track_time_interval(
            self.hass,
            _rediscover,
            timedelta(hours=2),
        )

    async def update_library_and_rediscover(self) -> None:
        """Update the library and rediscover entities."""
        library = await self._get_library()
        await library.initialize()
        await self.start_discovery()

    async def start_discovery(self) -> None:
        """Start the discovery procedure."""
        if self._status == DiscoveryStatus.IN_PROGRESS:
            _LOGGER.debug("Discovery already in progress, skipping new discovery run")
            return
        self._status = DiscoveryStatus.IN_PROGRESS
        await self.initialize_existing_entries()

        _LOGGER.debug("Start auto discovery")

        _LOGGER.debug("Start entity discovery")
        await self.perform_discovery(self.get_entities, self.create_entity_source, DiscoveryBy.ENTITY)  # type: ignore[arg-type]

        _LOGGER.debug("Start device discovery")
        await self.perform_discovery(self.get_devices, self.create_device_source, DiscoveryBy.DEVICE)  # type: ignore[arg-type]

        _LOGGER.debug("Done auto discovery")
        self._status = DiscoveryStatus.FINISHED

    async def initialize_existing_entries(self) -> None:
        """Build a list of config entries which are already setup, to prevent duplicate discovery flows"""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if not entry.unique_id:
                continue  # pragma: no cover

            self.initialized_flows.add(entry.unique_id)
            entity_id = entry.data.get(CONF_ENTITY_ID)
            if not entity_id or entity_id == DUMMY_ENTITY_ID:
                continue

            entity = await create_source_entity(str(entity_id), self.hass)
            if entity and entity.device_entry:
                self.initialized_flows.add(f"pc_{entity.device_entry.id}")
            self.initialized_flows.add(entity_id)

    def remove_initialized_flow(self, entry: ConfigEntry) -> None:
        """Remove a flow from the initialized flows."""
        if entry.unique_id:
            self.initialized_flows.discard(entry.unique_id)
        entity_id = entry.data.get(CONF_ENTITY_ID)
        if entity_id:
            self.initialized_flows.discard(entity_id)

    async def perform_discovery(
        self,
        source_provider: Callable[[], Awaitable[list]],
        source_creator: Callable[[er.RegistryEntry | dr.DeviceEntry], Awaitable[SourceEntity]],
        discovery_type: DiscoveryBy,
    ) -> None:
        """Generalized discovery procedure for entities and devices."""
        for source in await source_provider():
            log_identifier = source.entity_id if discovery_type == DiscoveryBy.ENTITY else source.id
            try:
                model_info = await self.extract_model_info_from_device_info(source)
                if not model_info:
                    continue

                source_entity = await source_creator(source)

                power_profiles = await self.discover_entity(source_entity, model_info, discovery_type)
                if not power_profiles:
                    _LOGGER.debug("%s: Model not found in library, skipping discovery", log_identifier)
                    continue

                unique_id = self.create_unique_id(
                    source_entity,
                    discovery_type,
                    power_profiles[0] if power_profiles else None,
                )

                if self._is_already_discovered(source_entity, unique_id):
                    _LOGGER.debug(
                        "%s: Already setup with discovery, skipping new discovery (unique_id=%s)",
                        log_identifier,
                        unique_id,
                    )
                    continue

                self._init_entity_discovery(model_info, unique_id, source_entity, log_identifier, power_profiles, {})
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "%s: Error during %s discovery: %s",
                    log_identifier,
                    discovery_type,
                    err,
                )

    async def discover_entity(
        self,
        source_entity: SourceEntity,
        model_info: ModelInfo,
        discovery_type: DiscoveryBy = DiscoveryBy.ENTITY,
    ) -> list[PowerProfile] | None:
        if source_entity.entity_entry and self.is_wled_light(model_info, source_entity.entity_entry):
            await self.init_wled_flow(model_info, source_entity)
            return None

        return await self.find_power_profiles(model_info, source_entity, discovery_type)

    async def create_entity_source(self, entity_entry: er.RegistryEntry) -> SourceEntity:
        """Create SourceEntity for an entity."""
        return await create_source_entity(entity_entry.entity_id, self.hass)

    @staticmethod
    async def create_device_source(device_entry: dr.DeviceEntry) -> SourceEntity:
        """Create SourceEntity for a device."""
        return SourceEntity(
            object_id=device_entry.name_by_user or device_entry.name or "",
            name=device_entry.name,
            entity_id=DUMMY_ENTITY_ID,
            domain="sensor",
            device_entry=device_entry,
        )

    @staticmethod
    def create_unique_id(source: SourceEntity, discovery_type: DiscoveryBy, power_profile: PowerProfile | None) -> str:
        """Generate a unique ID based on source and type."""
        if discovery_type == DiscoveryBy.DEVICE:
            device_id = source.object_id
            if source.device_entry:
                device_id = source.device_entry.id
            return f"pc_{device_id}"

        return get_or_create_unique_id({}, source, power_profile)

    async def find_power_profiles(
        self,
        model_info: ModelInfo,
        source_entity: SourceEntity,
        discovery_type: DiscoveryBy,
    ) -> list[PowerProfile] | None:
        """Find power profiles for a given entity."""
        library = await self._get_library()
        models = await library.find_models(model_info)
        if not models:
            return None

        power_profiles = []
        for model_info in models:
            profile = await get_power_profile(self.hass, {}, source_entity, model_info=model_info, process_variables=False)
            if not profile or profile.discovery_by != discovery_type:  # pragma: no cover
                continue
            if discovery_type == DiscoveryBy.ENTITY and not profile.is_entity_domain_supported(
                source_entity.entity_entry,  # type: ignore[arg-type]
            ):
                continue
            if profile.device_type in self._exclude_device_types:
                continue
            if self._exclude_self_usage_profiles and profile.only_self_usage:
                continue
            power_profiles.append(profile)

        return power_profiles

    async def init_wled_flow(self, model_info: ModelInfo, source_entity: SourceEntity) -> None:
        """Initialize the discovery flow for a WLED light."""
        if DeviceType.LIGHT in self._exclude_device_types:
            return
        unique_id = f"pc_{source_entity.device_entry.id}" if source_entity.device_entry else get_or_create_unique_id({}, source_entity, None)
        if self._is_already_discovered(source_entity, unique_id):
            _LOGGER.debug(
                "%s: Already setup with discovery, skipping new discovery (unique_id=%s)",
                source_entity.entity_id,
                unique_id,
            )
            return

        self._init_entity_discovery(
            model_info,
            unique_id,
            source_entity,
            source_entity.entity_id,
            power_profiles=None,
            extra_discovery_data={
                CONF_MODE: CalculationStrategy.WLED,
            },
        )

    @staticmethod
    def is_wled_light(model_info: ModelInfo, entity_entry: er.RegistryEntry) -> bool:
        """Check if the entity is a WLED light."""
        return (
            model_info.manufacturer == MANUFACTURER_WLED
            and entity_entry.domain == LIGHT_DOMAIN
            and not re.search("master|segment", str(entity_entry.original_name), flags=re.IGNORECASE)
            and not re.search("master|segment", str(entity_entry.entity_id), flags=re.IGNORECASE)
        )

    async def get_entities(self) -> list[er.RegistryEntry]:
        """Get all entities from entity registry which qualifies for discovery."""

        def _check_already_configured(entity: er.RegistryEntry) -> bool:
            has_user_config = self._is_user_configured(entity.entity_id)
            if has_user_config:
                _LOGGER.debug(
                    "%s: Entity is manually configured, skipping auto configuration",
                    entity.entity_id,
                )
            return has_user_config

        entity_filter = CompositeFilter(
            [
                CategoryFilter(
                    [
                        EntityCategory.CONFIG,
                        EntityCategory.DIAGNOSTIC,
                    ],
                ),
                LambdaFilter(_check_already_configured),
                LambdaFilter(lambda entity: entity.device_id is None),
                LambdaFilter(lambda entity: entity.platform == "mqtt" and "segment" in entity.entity_id),
                LambdaFilter(lambda entity: entity.platform in ["powercalc", "switch_as_x"]),
                NotFilter(DomainFilter(SUPPORTED_DOMAINS)),
            ],
            FilterOperator.OR,
        )
        return await get_filtered_entity_list(self.hass, NotFilter(entity_filter))

    async def get_devices(self) -> list:
        """Fetch device entries."""
        return list(dr.async_get(self.hass).devices.values())

    def enable(self) -> None:
        """Enable the discovery."""
        self._status = DiscoveryStatus.NOT_STARTED

    async def disable(self) -> None:
        """Disable the discovery."""
        self._status = DiscoveryStatus.DISABLED
        self.initialized_flows = set()
        flows = self.hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        for flow in flows:
            if flow["context"]["source"] != SOURCE_INTEGRATION_DISCOVERY:
                continue  # pragma: no cover
            self.hass.config_entries.flow.async_abort(flow["flow_id"])
        return

    async def extract_model_info_from_device_info(
        self,
        entry: er.RegistryEntry | dr.DeviceEntry | None,
    ) -> ModelInfo | None:
        """Try to auto discover manufacturer and model from the known device information."""
        if not entry:
            return None

        log_identifier = entry.entity_id if isinstance(entry, er.RegistryEntry) else entry.id

        if isinstance(entry, er.RegistryEntry):
            model_info = await self.get_model_information_from_entity(entry)
        else:
            model_info = await self.get_model_information_from_device(entry)
        if not model_info:
            _LOGGER.debug(
                "%s: Cannot autodiscover model, manufacturer or model unknown from device registry",
                log_identifier,
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
            "%s: Found model information on device (manufacturer=%s, model=%s, model_id=%s)",
            log_identifier,
            model_info.manufacturer,
            model_info.model,
            model_info.model_id,
        )
        return model_info

    @staticmethod
    async def get_model_information_from_device(device_entry: dr.DeviceEntry) -> ModelInfo | None:
        """See if we have enough information in device registry to automatically set up the power sensor."""
        if device_entry.manufacturer is None or device_entry.model is None:
            return None

        manufacturer = str(device_entry.manufacturer)
        model = str(device_entry.model)
        model_id = device_entry.model_id if hasattr(device_entry, "model_id") else None

        if len(manufacturer) == 0 or len(model) == 0:
            return None

        return ModelInfo(manufacturer, model, model_id)

    async def get_model_information_from_entity(self, entity_entry: er.RegistryEntry) -> ModelInfo | None:
        """See if we have enough information in device registry to automatically setup the power sensor."""
        if entity_entry.device_id is None:
            return None
        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get(entity_entry.device_id)
        if device_entry is None:
            return None

        return await self.get_model_information_from_device(device_entry)

    @callback
    def _init_entity_discovery(
        self,
        model_info: ModelInfo,
        unique_id: str,
        source_entity: SourceEntity,
        log_identifier: str,
        power_profiles: list[PowerProfile] | None,
        extra_discovery_data: dict | None,
    ) -> None:
        """Dispatch the discovery flow for a given entity."""

        discovery_data: dict[str, Any] = {
            CONF_ENTITY_ID: source_entity.entity_id,
            DISCOVERY_SOURCE_ENTITY: source_entity,
            CONF_UNIQUE_ID: unique_id,
        }

        if power_profiles:
            discovery_data[DISCOVERY_POWER_PROFILES] = power_profiles
            if len(power_profiles) == 1:
                power_profile = power_profiles[0]
                discovery_data[CONF_MANUFACTURER] = power_profile.manufacturer
                discovery_data[CONF_MODEL] = power_profile.model

        if CONF_MANUFACTURER not in discovery_data:
            discovery_data[CONF_MANUFACTURER] = model_info.manufacturer
        if CONF_MODEL not in discovery_data:
            discovery_data[CONF_MODEL] = model_info.model or model_info.model_id

        if extra_discovery_data:
            discovery_data.update(extra_discovery_data)

        self.initialized_flows.add(unique_id)
        if source_entity.entity_id != DUMMY_ENTITY_ID:
            self.initialized_flows.add(source_entity.entity_id)

        _LOGGER.debug("%s: Initiating discovery flow, unique_id=%s", log_identifier, unique_id)

        discovery_flow.async_create_flow(
            self.hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=discovery_data,
        )

    @property
    def status(self) -> DiscoveryStatus:
        """Get the discovery status"""
        return self._status

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

    def _is_already_discovered(self, source_entity: SourceEntity, unique_id: str) -> bool:
        """Prevent duplicate discovery flows."""
        unique_ids_to_check = [unique_id, source_entity.entity_id, source_entity.unique_id]
        if unique_id.startswith("pc_"):
            unique_ids_to_check.append(unique_id[3:])
        unique_ids_to_check.extend([f"pc_{uid}" for uid in unique_ids_to_check])

        return any(unique_id in self.initialized_flows for unique_id in unique_ids_to_check)

    async def _get_library(self) -> ProfileLibrary:
        """Get the powercalc library instance."""
        if not self.library:
            self.library = await ProfileLibrary.factory(self.hass)
        return self.library
