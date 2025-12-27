from __future__ import annotations

from asyncio import timeout
from collections import Counter
from collections.abc import Hashable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, Literal, TypedDict
import uuid

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION  # noqa
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from custom_components.powercalc.const import (
    API_URL,
    CONF_ENABLE_ANALYTICS,
    DATA_ANALYTICS,
    DATA_CONFIG_TYPES,
    DATA_GROUP_SIZES,
    DATA_GROUP_TYPES,
    DATA_HAS_GROUP_INCLUDE,
    DATA_POWER_PROFILES,
    DATA_SENSOR_TYPES,
    DATA_SOURCE_DOMAINS,
    DATA_STRATEGIES,
    DOMAIN,
    DOMAIN_CONFIG,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    CalculationStrategy,
    GroupType,
    SensorType,
)
from custom_components.powercalc.power_profile.library import ProfileLibrary
from custom_components.powercalc.power_profile.power_profile import PowerProfile
from custom_components.powercalc.sensors.group.config_entry_utils import get_entries_excluding_global_config

ENDPOINT_ANALYTICS = f"{API_URL}/analytics"
ANALYTICS_INTERVAL = timedelta(days=1)
STORAGE_KEY = "powercalc.analytics"
STORAGE_VERSION = 1

_LOGGER = logging.getLogger(__name__)

_SEEN_KEY: Literal["_seen"] = "_seen"


class RuntimeAnalyticsData(TypedDict, total=False):
    sensor_types: Counter[SensorType]
    config_types: Counter[str]
    strategies: Counter[CalculationStrategy]
    power_profiles: list[PowerProfile]
    source_domains: Counter[str]
    group_types: Counter[GroupType]
    group_sizes: list[int]
    uses_include: bool
    _seen: dict[str, set[str]]


@dataclass
class AnalyticsData:
    """Analytics data."""

    install_id: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyticsData:
        """Initialize analytics data from a dict."""
        return cls(
            data["install_id"],
        )


def collect_analytics(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None = None,
) -> AnalyticsCollector:
    """Return analytics collector instance"""
    analytics_data: RuntimeAnalyticsData = hass.data[DOMAIN][DATA_ANALYTICS]
    return AnalyticsCollector(analytics_data, config_entry)


class AnalyticsCollector:
    def __init__(
        self,
        data: RuntimeAnalyticsData,
        config_entry: ConfigEntry | None,
    ) -> None:
        self._data = data
        self._entry_id = config_entry.entry_id if config_entry else None
        self._seen: dict[str, set[str]] = data.setdefault(_SEEN_KEY, {})

    def _already_seen(self, key: str) -> bool:
        """Check whether we already collected analytics for a give config entry"""
        if not self._entry_id:
            return False

        seen_for_key = self._seen.setdefault(key, set())
        if self._entry_id in seen_for_key:
            return True

        seen_for_key.add(self._entry_id)
        return False

    def inc(self, key: str, value: Hashable) -> None:
        """Increment counter"""
        if self._already_seen(key):
            return

        counter: Counter[Hashable] = self._data.setdefault(key, Counter())  # type:ignore
        counter[value] += 1

    def add(self, key: str, value: Any) -> None:  # noqa: ANN401
        """Add value to listing"""
        if self._already_seen(key) or value is None:
            return

        lst: list[Any] = self._data.setdefault(key, [])  # type:ignore
        lst.append(value)

    def set_flag(self, key: str) -> None:
        """Set a boolean flag to True"""
        self._data[key] = True  # type:ignore


class Analytics:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.session = async_get_clientsession(hass)
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: AnalyticsData = AnalyticsData(install_id=None)

    async def load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._data = AnalyticsData.from_dict(stored)

    @property
    def install_id(self) -> str | None:
        return self._data.install_id

    async def _prepare_payload(self) -> dict:
        powercalc_integration = await async_get_integration(self.hass, DOMAIN)
        runtime_data: RuntimeAnalyticsData = self.hass.data[DOMAIN][DATA_ANALYTICS]
        power_profiles: list[PowerProfile] = runtime_data.get(DATA_POWER_PROFILES, [])
        group_sizes: list[int] = runtime_data.get(DATA_GROUP_SIZES, [])
        global_config_entry = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN,
            ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
        )
        payload: dict = {
            "install_id": self.install_id,
            "powercalc_version": powercalc_integration.version,
            "ha_version": HA_VERSION,
            "config_entry_count": len(get_entries_excluding_global_config(self.hass)),
            "custom_profile_count": await self._get_custom_profile_count(),
            "has_global_gui_config": global_config_entry is not None,
            "has_group_include": runtime_data.get(DATA_HAS_GROUP_INCLUDE, False),
            "group_sizes": Counter(group_sizes),
            "counts": {
                "by_config_type": runtime_data.setdefault(DATA_CONFIG_TYPES, Counter()),
                "by_device_type": Counter(profile.device_type for profile in power_profiles),
                "by_sensor_type": runtime_data.setdefault(DATA_SENSOR_TYPES, Counter()),
                "by_manufacturer": Counter(profile.manufacturer for profile in power_profiles),
                "by_model": Counter(f"{profile.manufacturer}:{profile.model}" for profile in power_profiles),
                "by_strategy": runtime_data.setdefault(DATA_STRATEGIES, Counter()),
                "by_source_domain": runtime_data.setdefault(DATA_SOURCE_DOMAINS, Counter()),
                "by_group_type": runtime_data.setdefault(DATA_GROUP_TYPES, Counter()),
            },
        }

        return payload

    async def _get_custom_profile_count(self) -> int:
        loader = ProfileLibrary.create_loader(self.hass, True)
        await loader.initialize()
        total = 0
        for manufacturer in await loader.get_manufacturer_listing(None):
            total += len(await loader.get_model_listing(manufacturer[0], None))
        return total

    async def send_analytics(self, _: datetime | None = None) -> None:
        """Send analytics."""
        global_config = self.hass.data.get(DOMAIN, {}).get(DOMAIN_CONFIG, {})
        if not global_config.get(CONF_ENABLE_ANALYTICS, False):
            _LOGGER.debug("Analytics is disabled in global configuration")
            return

        if self._data.install_id is None:
            self._data.install_id = str(uuid.uuid4())
            await self._store.async_save(asdict(self._data))

        payload = await self._prepare_payload()

        try:
            async with timeout(30):
                response = await self.session.post(ENDPOINT_ANALYTICS, json=payload)
                if 200 <= response.status < 300:
                    _LOGGER.info(
                        ("Submitted Powercalc analytics. Information submitted includes %s"),
                        payload,
                    )
                else:
                    _LOGGER.warning(
                        "Sending analytics failed with statuscode %s from %s",
                        response.status,
                        ENDPOINT_ANALYTICS,
                    )
        except TimeoutError:
            _LOGGER.error("Timeout sending analytics to %s", ENDPOINT_ANALYTICS)
        except aiohttp.ClientError as err:
            _LOGGER.error(
                "Error sending analytics to %s: %r",
                ENDPOINT_ANALYTICS,
                err,
            )
