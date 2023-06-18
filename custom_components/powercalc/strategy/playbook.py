from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import climate, vacuum  # type: ignore
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt

from .strategy_interface import PowerCalculationStrategyInterface
from ..const import CONF_PLAYBOOKS

# CONFIG_SCHEMA = vol.Schema(
#     {
#         vol.Optional(CONF_PLAYBOOKS): vol.Schema(
#             {cv.string: cv.string},
#         ),
#     },
# )

_LOGGER = logging.getLogger(__name__)


class PlaybookStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        self._hass = hass
        self._active_playbook: Playbook | None = None
        self._loaded_playbooks: dict[str, Playbook] = {}
        self._update_callback: Callable | None = None
        self._start_time: datetime | None = None
        self._cancel_timer = None

    def set_update_callback(self, update_callback: Callable):
        self._update_callback = update_callback

    async def calculate(self, entity_state: State) -> Decimal | None:
        return Decimal(0)

    async def activate_playbook(self, playbook_id: str) -> None:
        _LOGGER.debug("Activate playbook")
        playbook = await self._load_playbook(playbook_id=playbook_id)
        self._active_playbook = playbook
        self._start_time = dt.utcnow()

        self._execute_playbook_entry()

    @callback
    def _execute_playbook_entry(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

        queue = self._active_playbook.queue
        if len(queue) == 0:
            _LOGGER.debug("Playbook completed")
            return

        entry = queue.dequeue()

        @callback
        def _update_power(event: Event) -> None:
            power = Decimal(entry[1])
            _LOGGER.debug(f"Update power {power}")
            self._update_callback(power)
            # Schedule next update
            self._execute_playbook_entry()

        # Schedule update in the future
        self._cancel_timer = async_track_point_in_time(
            self._hass,
            _update_power,
            self._start_time + timedelta(seconds=entry[0])
        )

    async def _load_playbook(self, playbook_id: str) -> Playbook:
        if playbook_id in self._loaded_playbooks:
            return self._loaded_playbooks[playbook_id]

        # todo actual loading of playbooks
        queue = PlaybookQueue()
        queue.enqueue([5, 30])
        queue.enqueue([10, 40])
        queue.enqueue([15, 55])
        self._loaded_playbooks = Playbook(id=playbook_id, queue=queue)
        return self._loaded_playbooks


@dataclass
class Playbook:
    id: str
    queue: PlaybookQueue


class PlaybookQueue:
    def __init__(self):
        self._elements = deque()

    def enqueue(self, element):
        self._elements.append(element)

    def dequeue(self):
        return self._elements.popleft()

    def __len__(self):
        return len(self._elements)
