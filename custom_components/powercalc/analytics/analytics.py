from asyncio import timeout
from collections import defaultdict
from datetime import datetime, timedelta
import logging
import uuid

import aiohttp
from homeassistant.const import __version__ as HA_VERSION  # noqa
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from custom_components.powercalc.analytics.collection import get_manufacturer_counts, get_model_counts
from custom_components.powercalc.const import API_URL, DATA_ANALYTICS, DATA_SENSOR_TYPE_COUNTS, DOMAIN, SensorType

ENDPOINT_ANALYTICS = f"{API_URL}/analytics"
ANALYTICS_INTERVAL = timedelta(days=1)

_LOGGER = logging.getLogger(__name__)


class Analytics:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.session = async_get_clientsession(hass)

    async def _prepare_payload(self) -> dict:
        uid = str(uuid.uuid4())  # maybe take from HA analytics
        powercalc_integration = await async_get_integration(self.hass, DOMAIN)
        sensor_type_counts: dict[SensorType, int] = self.hass.data[DOMAIN][DATA_ANALYTICS].setdefault(DATA_SENSOR_TYPE_COUNTS, defaultdict(int))
        payload: dict = {
            "install_id": uid,
            "ts": "2025-12-13T08:12:00Z",
            "powercalc_version": powercalc_integration.version,
            "ha_version": HA_VERSION,
            "counts": sensor_type_counts,
            # "config_entry_count": 0,
            "by_manufacturer": get_manufacturer_counts(self.hass),
            "by_model": get_model_counts(self.hass),
        }
        return payload

    async def send_analytics(self, _: datetime | None = None) -> None:
        """Send analytics."""

        # Check opt-in
        # if not self.onboarded or not self.preferences.get(ATTR_BASE, False):
        #     LOGGER.debug("Nothing to submit")
        #     return

        # if self._data.uuid is None:
        #     self._data.uuid = gen_uuid()
        #     await self._store.async_save(dataclass_asdict(self._data))

        payload = await self._prepare_payload()

        try:
            async with timeout(30):
                response = await self.session.post(ENDPOINT_ANALYTICS, json=payload, headers={"Authorization": "Bearer foo"})
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
