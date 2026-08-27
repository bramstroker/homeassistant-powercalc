import asyncio
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import logging
import re
from typing import Any

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER, ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_PLATFORM, CONF_UNIQUE_ID
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant
from homeassistant.helpers import discovery_flow
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity import EntityCategory
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .common import SourceEntity, create_source_entity
from .const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSORS,
    DATA_DISCOVERY_MANAGER,
    DISCOVERY_INTEGRATION_NAME,
    DISCOVERY_POWER_PROFILES,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DUMMY_ENTITY_ID,
    MANUFACTURER_WLED,
    CalculationStrategy,
)
from .device_binding import (
    get_config_entry_ids,
    get_non_composite_devices,
    get_related_device_ids,
)
from .group_include.filter import (
    CategoryFilter,
    CompositeFilter,
    DomainFilter,
    FilterOperator,
    LambdaFilter,
    NotFilter,
    get_filtered_entity_list,
)
from .helpers import get_or_create_unique_id
from .power_profile.factory import get_power_profile
from .power_profile.library import ModelInfo, ProfileLibrary
from .power_profile.power_profile import (
    SUPPORTED_DOMAINS,
    DeviceType,
    DiscoveryBy,
    PowerProfile,
    is_device_type_supported_for_entity,
)

_LOGGER = logging.getLogger(__name__)

# Give Home Assistant a moment to settle before the first scan. Discovery walks the whole entity
# and device registry, which other integrations are still filling while they set up. Starting a
# little later keeps startup responsive and lets one pass see a more complete picture.
DISCOVERY_DELAY = timedelta(seconds=10)
REDISCOVERY_INTERVAL = timedelta(hours=2)
DISCOVERY_KEY_PREFIX = "pc_"


def device_discovery_key(device_id: str) -> str:
    """Build the discovery key identifying a device, prefixed to avoid conflicts with other integrations."""
    return f"{DISCOVERY_KEY_PREFIX}{device_id}"


def describe_power_profile(profile: PowerProfile) -> str:
    """Describe a power profile for logging purposes."""
    return (
        f"{profile.manufacturer}/{profile.model}"
        f"[device_type={profile.device_type}, strategy={profile.calculation_strategy}, "
        f"source={profile.configuration_source}]"
    )


def get_discovery_manager(hass: HomeAssistant) -> DiscoveryManager:
    """Return the shared discovery manager, creating a throwaway one when not yet set up."""
    try:
        return hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]  # type: ignore[no-any-return]
    except KeyError:
        return DiscoveryManager(hass, {})


async def _get_power_profile_by_source(
    hass: HomeAssistant,
    source_entity: SourceEntity,
    discovery_by: DiscoveryBy,
) -> PowerProfile | None:
    """Look up a power profile for a source entity, discovered either by entity or by device."""
    discovery_manager = get_discovery_manager(hass)
    model_info = discovery_manager.extract_model_info(source_entity)
    if not model_info:
        return None
    profiles = await discovery_manager.find_power_profiles(model_info, source_entity, discovery_by)
    return profiles[0] if profiles else None


async def get_power_profile_by_source_entity(hass: HomeAssistant, source_entity: SourceEntity) -> PowerProfile | None:
    """Given a certain entity, lookup the manufacturer and model and return the power profile."""
    if not source_entity.entity_entry:
        return None
    return await _get_power_profile_by_source(hass, source_entity, DiscoveryBy.ENTITY)


async def get_power_profile_by_source_device(hass: HomeAssistant, source_entity: SourceEntity) -> PowerProfile | None:
    """Look up a device-discovered power profile for a source entity's device."""
    if not source_entity.device_entry or not source_entity.entity_entry:
        return None
    return await _get_power_profile_by_source(hass, source_entity, DiscoveryBy.DEVICE)


class DiscoveryStatus(StrEnum):
    DISABLED = "disabled"
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    """Normalized source considered during a discovery run."""

    source_entity: SourceEntity
    discovery_type: DiscoveryBy
    integration_domains: frozenset[str]

    @property
    def log_identifier(self) -> str:
        """Label used as prefix for all log messages about this candidate."""
        return self.source_entity.log_identifier


@dataclass(slots=True)
class DiscoveryStats:
    """Counters describing the outcome of a single discovery phase.

    Logged as a summary after every phase, so an issue report shows at which step a device
    dropped out of discovery, without having to walk through thousands of individual log lines.
    """

    candidates: int = 0
    low_priority_integration: int = 0
    no_model_info: int = 0
    no_profile_match: int = 0
    already_configured: int = 0
    flows_initiated: int = 0
    errors: int = 0

    def __str__(self) -> str:
        return ", ".join(f"{key}={value}" for key, value in asdict(self).items())


@dataclass(frozen=True, slots=True)
class DiscoveryMatch:
    """Information needed to create a discovery flow for a candidate."""

    power_profiles: list[PowerProfile] | None = None
    extra_data: dict[str, Any] | None = None
    unique_id: str | None = None


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
        self._manually_configured_entities: set[str] | None = None
        self._configured_discovery_keys: set[str] = set()
        self._pending_discovery_keys: set[str] = set()
        self._library: ProfileLibrary | None = None
        self._exclude_device_types = set(exclude_device_types or [])
        self._exclude_self_usage_profiles = exclude_self_usage_profiles
        self._cancel_library_update_interval: CALLBACK_TYPE | None = None
        self._cancel_initial_discovery: CALLBACK_TYPE | None = None
        self._status = DiscoveryStatus.NOT_STARTED if enabled else DiscoveryStatus.DISABLED

    def setup(self) -> None:
        """Setup the discovery manager. Schedule the library update interval and initial discovery.

        The library update is scheduled regardless of the discovery status. Startup deliberately
        loads the library from local storage, so this interval is what keeps it up to date, and
        manually configured sensors depend on the library just as much as discovered ones.
        `start_discovery` is a no-op while discovery is disabled.
        """
        self._schedule_library_update()

        if self._status == DiscoveryStatus.DISABLED:
            _LOGGER.debug("Discovery manager is disabled, skipping initial discovery")
            return

        self._schedule_initial_discovery()

    def _schedule_library_update(self) -> None:
        """Refresh the library from the download API every REDISCOVERY_INTERVAL, then rediscover."""

        async def _rediscover(_: datetime) -> None:
            """Update the library and rediscover entities."""
            await self.update_library_and_rediscover()

        if self._cancel_library_update_interval:
            self._cancel_library_update_interval()

        self._cancel_library_update_interval = async_track_time_interval(
            self.hass,
            _rediscover,
            REDISCOVERY_INTERVAL,
            cancel_on_shutdown=True,
        )

    def _schedule_initial_discovery(self) -> None:
        """Start the first discovery run after DISCOVERY_DELAY, instead of during setup."""
        if self._cancel_initial_discovery:  # pragma: no cover
            self._cancel_initial_discovery()

        async def _start_discovery(_: datetime) -> None:
            self._cancel_initial_discovery = None
            # Nothing awaits this task, so handle failures here instead of leaving Home Assistant
            # to report them as an unretrieved task exception.
            try:
                await self.start_discovery()
            except asyncio.CancelledError:
                if not self.hass.is_stopping:
                    raise
                _LOGGER.debug("Initial discovery cancelled, Home Assistant is stopping")
            except Exception:
                if self.hass.is_stopping:
                    _LOGGER.debug("Initial discovery aborted, Home Assistant is stopping")
                else:
                    _LOGGER.exception("Error during initial discovery")

        _LOGGER.debug("Scheduling initial discovery in %s seconds", DISCOVERY_DELAY.total_seconds())
        self._cancel_initial_discovery = async_call_later(
            self.hass,
            DISCOVERY_DELAY,
            HassJob(_start_discovery, "powercalc initial discovery", cancel_on_shutdown=True),
        )

    async def update_library_and_rediscover(self) -> None:
        """Update the library and rediscover entities."""
        library = await self._get_library()
        await library.initialize(prefer_cached=False)
        await self.start_discovery()

    async def start_discovery(self) -> None:
        """Start the discovery procedure."""
        if self._status == DiscoveryStatus.DISABLED:
            _LOGGER.debug("Discovery manager is disabled, skipping discovery run")
            return
        if self._status == DiscoveryStatus.IN_PROGRESS:
            _LOGGER.debug("Discovery already in progress, skipping new discovery run")
            return
        self._status = DiscoveryStatus.IN_PROGRESS
        try:
            self.initialize_existing_entries()

            devices = self.get_devices()
            devices_by_config_entry = self._index_devices_by_config_entry(devices)

            _LOGGER.debug(
                "Start auto discovery (devices=%d, powercalc_entries=%d, configured_discovery_keys=%d, "
                "excluded_device_types=[%s], exclude_self_usage_profiles=%s)",
                len(devices),
                len(self.hass.config_entries.async_entries(DOMAIN)),
                len(self._configured_discovery_keys),
                ",".join(sorted(self._exclude_device_types)),
                self._exclude_self_usage_profiles,
            )

            _LOGGER.debug("Start entity discovery")
            entity_stats = await self.perform_discovery(self._create_entity_candidates())
            _LOGGER.debug("Done entity discovery (%s)", entity_stats)

            _LOGGER.debug("Start device discovery")
            device_stats = await self.perform_discovery(self._create_device_candidates(devices))
            _LOGGER.debug("Done device discovery (%s)", device_stats)

            _LOGGER.debug("Start config entry discovery")
            config_entry_stats = await self.perform_discovery(
                self._create_config_entry_candidates(devices_by_config_entry),
            )
            _LOGGER.debug("Done config entry discovery (%s)", config_entry_stats)

            _LOGGER.debug(
                "Done auto discovery, initiated %d discovery flow(s)",
                entity_stats.flows_initiated + device_stats.flows_initiated + config_entry_stats.flows_initiated,
            )
        finally:
            self._status = DiscoveryStatus.FINISHED

    def initialize_existing_entries(self) -> None:
        """Build a list of config entries which are already setup, to prevent duplicate discovery flows"""
        self._configured_discovery_keys = self._collect_configured_discovery_keys()

    def _collect_configured_discovery_keys(self, excluded_entry_id: str | None = None) -> set[str]:
        """Collect discovery keys claimed by existing config entries."""
        keys: set[str] = set()
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if not entry.unique_id or entry.entry_id == excluded_entry_id:
                continue  # pragma: no cover
            keys.update(self._discovery_keys_for_entry(entry))
        return keys

    def _discovery_keys_for_entry(self, entry: ConfigEntry) -> set[str]:
        """Return all discovery keys claimed by a config entry.

        A single physical device can be represented by several device registry entries. HA >=2026.8
        splits devices belonging to multiple config entries into one device per entry, so the entry
        may hold the composite device ID, which no longer resolves to a registered device, or one of
        the split devices after the user resolved the composite device repair. Devices can also be
        registered by several integrations, in which case they share identifiers or connections.
        All of them are the device the user already configured, so none should be discovered again.
        """
        keys = {entry.unique_id} if entry.unique_id else set()

        entity_id = entry.data.get(CONF_ENTITY_ID)
        if entity_id and entity_id != DUMMY_ENTITY_ID:
            entity_id = str(entity_id)
            keys.add(entity_id)
            entity_entry = er.async_get(self.hass).async_get(entity_id)
            if entity_entry and entity_entry.device_id:
                keys.add(device_discovery_key(entity_entry.device_id))

        device_id = entry.data.get(CONF_DEVICE)
        if not device_id:
            return keys

        for related_device_id in get_related_device_ids(self.hass, str(device_id)):
            keys.add(device_discovery_key(related_device_id))
        return keys

    def remove_initialized_flow(self, entry: ConfigEntry) -> None:
        """Remove a flow from the initialized flows."""
        self._pending_discovery_keys.difference_update(self._discovery_keys_for_entry(entry))
        self._configured_discovery_keys = self._collect_configured_discovery_keys(entry.entry_id)

    async def perform_discovery(
        self,
        candidates: Iterable[DiscoveryCandidate],
    ) -> DiscoveryStats:
        """Discover profiles and create flows for normalized candidates."""
        library = await self._get_library()
        low_priority_domains = library.discovery_low_priority_domains
        stats = DiscoveryStats()
        # Device candidates from low priority integrations go last, so a device represented by
        # several integrations is discovered through the preferred one, and only falls back to
        # the low priority representation when nothing better matched a profile.
        ordered_candidates = sorted(
            candidates,
            key=lambda candidate: (
                candidate.discovery_type == DiscoveryBy.DEVICE
                and bool(candidate.integration_domains & low_priority_domains)
            ),
        )
        for candidate in ordered_candidates:
            stats.candidates += 1
            try:
                await self._discover_candidate(candidate, low_priority_domains, stats)
            except Exception:
                stats.errors += 1
                _LOGGER.exception(
                    "%s: Error during %s discovery",
                    candidate.log_identifier,
                    candidate.discovery_type,
                )
        return stats

    async def _discover_candidate(
        self,
        candidate: DiscoveryCandidate,
        low_priority_domains: set[str],
        stats: DiscoveryStats,
    ) -> None:
        """Discover a single candidate and create a flow for it when it matches a profile."""
        matched_low_priority_domains = candidate.integration_domains & low_priority_domains
        if candidate.discovery_type != DiscoveryBy.DEVICE and matched_low_priority_domains:
            stats.low_priority_integration += 1
            _LOGGER.debug(
                "%s: Integration domain has low discovery priority, skipping discovery (domains=[%s])",
                candidate.log_identifier,
                ",".join(sorted(matched_low_priority_domains)),
            )
            return

        source_entity = candidate.source_entity
        model_info = self.extract_model_info(source_entity)
        if not model_info:
            stats.no_model_info += 1
            return

        match = await self._find_discovery_match(source_entity, model_info, candidate.discovery_type)
        if not match:
            stats.no_profile_match += 1
            _LOGGER.debug(
                "%s: Model not found in library, skipping discovery (discovery_by=%s)",
                candidate.log_identifier,
                candidate.discovery_type,
            )
            return

        unique_id = match.unique_id or self.create_unique_id(
            candidate, match.power_profiles[0] if match.power_profiles else None
        )

        if self._is_already_discovered(candidate, unique_id):
            stats.already_configured += 1
            _LOGGER.debug(
                "%s: Already setup with discovery, skipping new discovery (unique_id=%s)",
                candidate.log_identifier,
                unique_id,
            )
            return

        await self._init_entity_discovery(
            candidate,
            model_info,
            unique_id,
            match.power_profiles,
            match.extra_data,
        )
        stats.flows_initiated += 1

    async def _find_discovery_match(
        self,
        source_entity: SourceEntity,
        model_info: ModelInfo,
        discovery_type: DiscoveryBy,
    ) -> DiscoveryMatch | None:
        """Resolve a candidate to either a library profile or a special discovery mode."""
        if source_entity.entity_entry and self.is_wled_light(model_info, source_entity.entity_entry):
            if DeviceType.LIGHT in self._exclude_device_types:
                return None
            unique_id = (
                device_discovery_key(source_entity.device_id)
                if source_entity.device_id
                else get_or_create_unique_id({}, source_entity, None)
            )
            return DiscoveryMatch(extra_data={CONF_MODE: CalculationStrategy.WLED}, unique_id=unique_id)

        power_profiles = await self.find_power_profiles(model_info, source_entity, discovery_type)
        return DiscoveryMatch(power_profiles=power_profiles) if power_profiles else None

    def _create_entity_candidates(self) -> Iterator[DiscoveryCandidate]:
        """Yield normalized entity discovery candidates."""
        for entity_entry in self.get_entities():
            yield DiscoveryCandidate(
                source_entity=create_source_entity(entity_entry.entity_id, self.hass),
                discovery_type=DiscoveryBy.ENTITY,
                integration_domains=frozenset({entity_entry.platform}),
            )

    def _create_device_candidates(self, devices: Iterable[dr.DeviceEntry]) -> Iterator[DiscoveryCandidate]:
        """Yield normalized device discovery candidates."""
        for device_entry in devices:
            yield DiscoveryCandidate(
                source_entity=self.create_device_source(device_entry),
                discovery_type=DiscoveryBy.DEVICE,
                integration_domains=self._get_integration_domains(get_config_entry_ids(device_entry)),
            )

    def _create_config_entry_candidates(
        self,
        devices_by_config_entry: dict[str, list[dr.DeviceEntry]],
    ) -> Iterator[DiscoveryCandidate]:
        """Yield normalized config-entry discovery candidates."""
        for config_entry in self.get_config_entries(devices_by_config_entry):
            yield DiscoveryCandidate(
                source_entity=self.create_config_entry_source(
                    config_entry,
                    devices_by_config_entry[config_entry.entry_id][0],
                ),
                discovery_type=DiscoveryBy.CONFIG_ENTRY,
                integration_domains=frozenset({config_entry.domain}),
            )

    def _get_integration_domains(self, config_entry_ids: Iterable[str]) -> frozenset[str]:
        """Resolve config entry IDs to integration domains."""
        return frozenset(
            entry.domain
            for config_entry_id in config_entry_ids
            if (entry := self.hass.config_entries.async_get_entry(config_entry_id)) is not None
        )

    @staticmethod
    def create_device_source(device_entry: dr.DeviceEntry) -> SourceEntity:
        """Create SourceEntity for a device."""
        return SourceEntity(
            object_id=device_entry.name_by_user or device_entry.name or "",
            name=device_entry.name,
            entity_id=DUMMY_ENTITY_ID,
            domain=SENSOR_DOMAIN,
            device_entry=device_entry,
        )

    @staticmethod
    def create_config_entry_source(config_entry: ConfigEntry, device_entry: dr.DeviceEntry) -> SourceEntity:
        """Create a source representing all devices belonging to a config entry."""
        return SourceEntity(
            object_id=config_entry.entry_id,
            name=config_entry.title,
            entity_id=DUMMY_ENTITY_ID,
            domain=SENSOR_DOMAIN,
            device_entry=device_entry,
            config_entry_id=config_entry.entry_id,
        )

    @staticmethod
    def create_unique_id(candidate: DiscoveryCandidate, power_profile: PowerProfile | None) -> str:
        """Generate a unique ID for a discovery candidate."""
        source = candidate.source_entity

        if candidate.discovery_type == DiscoveryBy.CONFIG_ENTRY:
            config_entry_id = source.config_entry_id or source.object_id
            return device_discovery_key(f"config_entry_{config_entry_id}")

        if candidate.discovery_type == DiscoveryBy.DEVICE:
            return device_discovery_key(source.device_id or source.object_id)

        return get_or_create_unique_id({}, source, power_profile)

    async def find_power_profiles(
        self,
        model_info: ModelInfo,
        source_entity: SourceEntity,
        discovery_type: DiscoveryBy,
    ) -> list[PowerProfile]:
        """Find power profiles for a given entity."""
        library = await self._get_library()
        models = await library.find_models(model_info)
        log_identifier = source_entity.log_identifier
        if not models:
            _LOGGER.debug(
                "%s: No library models found (manufacturer=%s, model=%s, model_id=%s)",
                log_identifier,
                model_info.manufacturer,
                model_info.model,
                model_info.model_id,
            )
            return []

        _LOGGER.debug(
            "%s: Found %d matching library model(s): [%s]",
            log_identifier,
            len(models),
            ",".join(f"{model.manufacturer}/{model.model}" for model in models),
        )

        power_profiles = []
        for found_model in models:
            model_identifier = f"{found_model.manufacturer}/{found_model.model}"
            metadata = await library.get_model_metadata(found_model)
            if metadata and (
                reason := self._check_discovery_constraints(
                    metadata.device_type,
                    metadata.discovery_by,
                    source_entity,
                    discovery_type,
                )
            ):
                _LOGGER.debug("%s: Skipping model %s, %s", log_identifier, model_identifier, reason)
                continue

            profile = await get_power_profile(
                self.hass,
                {},
                source_entity,
                model_info=found_model,
                process_variables=False,
                model_resolved=True,
            )
            if not profile:
                _LOGGER.debug("%s: Could not load profile %s, skipping model", log_identifier, model_identifier)
                continue
            if reason := self._check_profile(profile, source_entity, discovery_type):
                _LOGGER.debug("%s: Skipping profile %s, %s", log_identifier, describe_power_profile(profile), reason)
                continue
            power_profiles.append(profile)

        return power_profiles

    def _check_profile(
        self,
        profile: PowerProfile,
        source_entity: SourceEntity,
        discovery_type: DiscoveryBy,
    ) -> str | None:
        """Return the reason a loaded profile is not eligible for a discovery candidate, None when it is."""
        reason = self._check_discovery_constraints(
            profile.device_type,
            profile.discovery_by,
            source_entity,
            discovery_type,
        )
        if reason:
            return reason
        if self._exclude_self_usage_profiles and profile.only_self_usage:
            return "self usage profiles are excluded by configuration"

        entity_entry = source_entity.entity_entry
        if (
            discovery_type == DiscoveryBy.ENTITY
            and entity_entry
            and profile.compatible_integrations
            and entity_entry.platform not in profile.compatible_integrations
        ):
            return (
                f"integration {entity_entry.platform} is not compatible with the profile "
                f"(compatible_integrations=[{','.join(profile.compatible_integrations or [])}])"
            )
        return None

    def _check_discovery_constraints(
        self,
        device_type: DeviceType | None,
        profile_discovery_type: DiscoveryBy,
        source_entity: SourceEntity,
        requested_discovery_type: DiscoveryBy,
    ) -> str | None:
        """Return the reason a candidate violates the constraints shared by indexed metadata and loaded profiles.

        Called with indexed metadata before building a profile, to skip models which can never match.
        The index is only authoritative for the properties checked here. Everything it does not carry,
        such as `only_self_usage` and `compatible_integrations`, is still checked on the profile
        itself, so the metadata pass can only save work, never change the outcome.
        """
        if profile_discovery_type != requested_discovery_type:
            return (
                f"profile is discovered by {profile_discovery_type}, "
                f"candidate is discovered by {requested_discovery_type}"
            )
        if device_type in self._exclude_device_types:
            return f"device type {device_type} is excluded by configuration"
        if (
            requested_discovery_type == DiscoveryBy.ENTITY
            and source_entity.entity_entry is not None
            and not is_device_type_supported_for_entity(device_type, source_entity.entity_entry)
        ):
            return f"device type {device_type} is not supported for entity domain {source_entity.entity_entry.domain}"
        return None

    @staticmethod
    def is_wled_light(model_info: ModelInfo, entity_entry: er.RegistryEntry) -> bool:
        """Check if the entity is a WLED light."""
        return (
            model_info.manufacturer == MANUFACTURER_WLED
            and entity_entry.domain == LIGHT_DOMAIN
            and not re.search("master|segment", str(entity_entry.original_name), flags=re.IGNORECASE)
            and not re.search("master|segment", str(entity_entry.entity_id), flags=re.IGNORECASE)
        )

    def get_entities(self) -> list[er.RegistryEntry]:
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
        return get_filtered_entity_list(self.hass, NotFilter(entity_filter))

    def get_devices(self) -> list[dr.DeviceEntry]:
        """Fetch device entries."""
        return get_non_composite_devices(self.hass)

    @staticmethod
    def _index_devices_by_config_entry(
        devices: Iterable[dr.DeviceEntry],
    ) -> dict[str, list[dr.DeviceEntry]]:
        """Group devices by their owning config entry without rescanning the registry."""
        devices_by_config_entry: defaultdict[str, list[dr.DeviceEntry]] = defaultdict(list)
        for device in devices:
            for config_entry_id in get_config_entry_ids(device):
                devices_by_config_entry[config_entry_id].append(device)
        return dict(devices_by_config_entry)

    def get_config_entries(
        self,
        devices_by_config_entry: dict[str, list[dr.DeviceEntry]] | None = None,
    ) -> list[ConfigEntry]:
        """Fetch config entries which have at least one non-composite device."""
        if devices_by_config_entry is None:
            devices_by_config_entry = self._index_devices_by_config_entry(self.get_devices())
        return [
            entry
            for entry in self.hass.config_entries.async_entries()
            if entry.domain != DOMAIN and entry.entry_id in devices_by_config_entry
        ]

    def enable(self) -> None:
        """Enable the discovery."""
        self._status = DiscoveryStatus.NOT_STARTED

    async def disable(self) -> None:
        """Disable the discovery.

        The library update interval is deliberately kept running: manually configured sensors
        still need up to date profiles. `start_discovery` returns early while disabled.
        """
        if self._cancel_initial_discovery:
            self._cancel_initial_discovery()
            self._cancel_initial_discovery = None
        self._status = DiscoveryStatus.DISABLED
        self._configured_discovery_keys.clear()
        self._pending_discovery_keys.clear()
        flows = self.hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        for flow in flows:
            if flow["context"]["source"] != SOURCE_INTEGRATION_DISCOVERY:
                continue  # pragma: no cover
            self.hass.config_entries.flow.async_abort(flow["flow_id"])

    def extract_model_info(self, source_entity: SourceEntity) -> ModelInfo | None:
        """Try to fetch manufacturer and model from the known device information."""
        device_entry = source_entity.device_entry
        if not isinstance(device_entry, dr.DeviceEntry):
            return None

        log_identifier = source_entity.log_identifier
        device_id = device_entry.id
        model_info = self.get_model_information_from_device(device_entry)

        if not model_info:
            _LOGGER.debug(
                "%s: Cannot autodiscover model, manufacturer or model unknown from device registry (device_id=%s)",
                log_identifier,
                device_id,
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
            "%s: Found model information on device (manufacturer=%s, model=%s, model_id=%s, device_id=%s)",
            log_identifier,
            model_info.manufacturer,
            model_info.model,
            model_info.model_id,
            device_id,
        )
        return model_info

    @staticmethod
    def get_model_information_from_device(device_entry: dr.DeviceEntry) -> ModelInfo | None:
        """See if we have enough information in device registry to automatically set up the power sensor."""
        if device_entry.manufacturer is None or device_entry.model is None:
            return None

        # Strip whitespace: some integrations include trailing spaces
        # see https://github.com/home-assistant/core/pull/166187
        manufacturer = str(device_entry.manufacturer).strip()
        model = str(device_entry.model).strip()
        model_id = (
            str(device_entry.model_id).strip() if hasattr(device_entry, "model_id") and device_entry.model_id else None
        )

        if len(manufacturer) == 0 or len(model) == 0:
            return None

        return ModelInfo(manufacturer, model, model_id)

    async def _init_entity_discovery(
        self,
        candidate: DiscoveryCandidate,
        model_info: ModelInfo,
        unique_id: str,
        power_profiles: list[PowerProfile] | None,
        extra_discovery_data: dict[str, Any] | None,
    ) -> None:
        """Dispatch the discovery flow for a given entity."""
        source_entity = candidate.source_entity
        integration_name = await self._get_integration_name(source_entity)

        discovery_data: dict[str, Any] = {
            CONF_ENTITY_ID: source_entity.entity_id,
            DISCOVERY_INTEGRATION_NAME: integration_name,
            DISCOVERY_SOURCE_ENTITY: source_entity,
            CONF_UNIQUE_ID: unique_id,
        }

        if power_profiles:
            discovery_data[DISCOVERY_POWER_PROFILES] = power_profiles
            if len(power_profiles) == 1:
                power_profile = power_profiles[0]
                discovery_data[CONF_MANUFACTURER] = power_profile.manufacturer
                discovery_data[CONF_MODEL] = power_profile.model

        discovery_data.setdefault(CONF_MANUFACTURER, model_info.manufacturer)
        discovery_data.setdefault(CONF_MODEL, model_info.model or model_info.model_id)

        if extra_discovery_data:
            discovery_data.update(extra_discovery_data)

        self._pending_discovery_keys.add(unique_id)
        if not source_entity.is_dummy:
            self._pending_discovery_keys.add(source_entity.entity_id)

        _LOGGER.debug(
            "%s: Initiating discovery flow, discovery_by=%s, unique_id=%s, integration=%s, integration_domains=[%s], "
            "device_id=%s, source_domain=%s, manufacturer=%s, model=%s, model_id=%s, profiles=[%s], extra_data=%s",
            candidate.log_identifier,
            candidate.discovery_type,
            unique_id,
            integration_name,
            ",".join(sorted(candidate.integration_domains)),
            source_entity.device_id,
            source_entity.domain,
            discovery_data[CONF_MANUFACTURER],
            discovery_data[CONF_MODEL],
            model_info.model_id,
            ", ".join(describe_power_profile(profile) for profile in power_profiles or []),
            extra_discovery_data,
        )

        discovery_flow.async_create_flow(
            self.hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=discovery_data,
        )

    async def _get_integration_name(self, source_entity: SourceEntity) -> str | None:
        """Return the display name of the integration which owns the discovery source."""
        config_entry_id = source_entity.config_entry_id
        if config_entry_id is None and source_entity.entity_entry:
            config_entry_id = source_entity.entity_entry.config_entry_id
        if config_entry_id is None and source_entity.device_entry:
            config_entry_id = next(iter(get_config_entry_ids(source_entity.device_entry)), None)
        if config_entry_id is None:
            return None

        config_entry = self.hass.config_entries.async_get_entry(config_entry_id)
        if config_entry is None:
            return None

        try:
            integration = await async_get_integration(self.hass, config_entry.domain)
        except IntegrationNotFound:
            _LOGGER.debug("Unable to resolve integration name for domain %s", config_entry.domain)
            return None
        return integration.name

    @property
    def status(self) -> DiscoveryStatus:
        """Get the discovery status"""
        return self._status

    def _is_user_configured(self, entity_id: str) -> bool:
        """Check if user have setup powercalc sensors for a given entity_id.
        Either with the YAML or GUI method.
        """
        # Explicit None check: when nothing is configured manually the result is an empty set,
        # which would otherwise be reloaded for every single entity.
        if self._manually_configured_entities is None:
            self._manually_configured_entities = self._load_manually_configured_entities()

        return entity_id in self._manually_configured_entities

    def _load_manually_configured_entities(self) -> set[str]:
        """Looks at the YAML and GUI config entries for all the configured entity_id's."""
        entities: set[str] = set()

        # Find entity ids in yaml config (Legacy)
        if SENSOR_DOMAIN in self.ha_config:  # pragma: no cover
            sensor_config = self.ha_config.get(SENSOR_DOMAIN)
            platform_entries = [
                item for item in sensor_config or {} if isinstance(item, dict) and item.get(CONF_PLATFORM) == DOMAIN
            ]
            for entry in platform_entries:
                entities.update(self._iter_entity_ids(entry))

        # Find entity ids in yaml config (New)
        domain_config: ConfigType = self.ha_config.get(DOMAIN, {})
        if CONF_SENSORS in domain_config:
            sensors = domain_config[CONF_SENSORS]
            for sensor_config in sensors:
                entities.update(self._iter_entity_ids(sensor_config))

        # Add entities from existing config entries
        entities.update(
            entity_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.source == SOURCE_USER
            if isinstance((entity_id := entry.data.get(CONF_ENTITY_ID)), str)
        )
        return entities

    def _iter_entity_ids(self, value: object) -> Iterator[str]:
        """Yield entity IDs from nested Powercalc YAML configuration."""
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if key == CONF_ENTITY_ID:
                    yield from self._iter_configured_entity_ids(nested_value)
                else:
                    yield from self._iter_entity_ids(nested_value)
        elif isinstance(value, list):
            for item in value:
                yield from self._iter_entity_ids(item)

    @staticmethod
    def _iter_configured_entity_ids(value: object) -> Iterator[str]:
        """Yield the entity IDs of a single `entity_id` configuration option."""
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            yield from (item for item in value if isinstance(item, str))

    def _is_already_discovered(self, candidate: DiscoveryCandidate, unique_id: str) -> bool:
        """Prevent duplicate discovery flows."""
        source_entity = candidate.source_entity
        unique_ids_to_check = {
            key for key in (unique_id, source_entity.entity_id, source_entity.unique_id) if key is not None
        }
        if unique_id.startswith(DISCOVERY_KEY_PREFIX):
            unique_ids_to_check.add(unique_id.removeprefix(DISCOVERY_KEY_PREFIX))

        if candidate.discovery_type == DiscoveryBy.DEVICE and source_entity.device_id:
            unique_ids_to_check.update(get_related_device_ids(self.hass, source_entity.device_id))

        unique_ids_to_check.update({device_discovery_key(uid) for uid in unique_ids_to_check})

        return not (
            unique_ids_to_check.isdisjoint(self._configured_discovery_keys)
            and unique_ids_to_check.isdisjoint(self._pending_discovery_keys)
        )

    async def _get_library(self) -> ProfileLibrary:
        """Get the powercalc library instance."""
        if not self._library:
            self._library = await ProfileLibrary.factory(self.hass)
        return self._library
