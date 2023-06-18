from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import climate, vacuum  # type: ignore
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import TrackTemplate, async_track_point_in_time
from homeassistant.helpers.template import Template
from homeassistant.util import dt

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_POWER, CONF_STATES_POWER
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.helpers import evaluate_power

from .strategy_interface import PowerCalculationStrategyInterface

# CONFIG_SCHEMA = vol.Schema(
#     {
#         vol.Optional(CONF_POWER): vol.Any(vol.Coerce(float), cv.template),
#         vol.Optional(CONF_STATES_POWER): vol.Schema(
#             {cv.string: vol.Any(vol.Coerce(float), cv.template)},
#         ),
#     },
# )

_LOGGER = logging.getLogger(__name__)


class PlaybookStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        hass: HomeAssistant,
        update_callback: Callable
    ) -> None:
        self._hass = hass
        self._update_callback = update_callback
        self._active_playbook: str | None = None
        self._event_removals: list = []

    async def calculate(self, entity_state: State) -> Decimal | None:
        return None

    async def activate_playbook(self) -> None:
        _LOGGER.debug("Activate playbook")

        @callback
        def update_power(power):
            self._update_callback(power)

        self._event_removals.append(async_track_point_in_time(self._hass, self._update_callback, dt.utcnow() + timedelta(seconds=5)))
        self._event_removals.append(async_track_point_in_time(self._hass, self._update_callback, dt.utcnow() + timedelta(seconds=10)))

