from __future__ import annotations

from asyncio import timeout
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, TypedDict
import uuid

import aiohttp
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
    DATA_POWER_PROFILES,
    DATA_SENSOR_TYPES,
    DATA_STRATEGIES,
    DOMAIN,
    DOMAIN_CONFIG,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    CalculationStrategy,
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


class RuntimeAnalyticsData(TypedDict, total=False):
    sensor_types: Counter[SensorType]
    config_types: Counter[str]
    strategies: Counter[CalculationStrategy]
    power_profiles: list[PowerProfile]


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
            "counts": {
                "by_config_type": runtime_data.setdefault(DATA_CONFIG_TYPES, Counter()),
                "by_sensor_type": runtime_data.setdefault(DATA_SENSOR_TYPES, Counter()),
                "by_manufacturer": self._get_manufacturer_counts(),
                "by_model": self._get_model_counts(),
                "by_strategy": runtime_data.setdefault(DATA_STRATEGIES, Counter()),
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

    def _get_manufacturer_counts(self) -> dict[str, int]:
        profiles: list[PowerProfile] = self.hass.data[DOMAIN][DATA_ANALYTICS].setdefault(DATA_POWER_PROFILES, [])
        counts: dict[str, int] = defaultdict(int)

        for profile in profiles:
            counts[profile.manufacturer] += 1

        return dict(counts)

    def _get_model_counts(self) -> dict[str, int]:
        profiles: list[PowerProfile] = self.hass.data[DOMAIN][DATA_ANALYTICS].setdefault(DATA_POWER_PROFILES, [])
        counts: dict[str, int] = defaultdict(int)

        for profile in profiles:
            key = f"{profile.manufacturer}:{profile.model}"
            counts[key] += 1

        return dict(counts)

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
                if response.status == 204:
                    _LOGGER.error(
                        ("Submitted Powercalc analytics. Information submitted includes %s"),
                        payload,
                    )
                else:
                    _LOGGER.error(
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
