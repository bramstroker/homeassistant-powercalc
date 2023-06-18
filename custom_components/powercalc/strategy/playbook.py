from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import ConfigType
from homeassistant.helpers.event import async_track_point_in_time
import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt

from .strategy_interface import PowerCalculationStrategyInterface
from ..const import CONF_PLAYBOOKS

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PLAYBOOKS): vol.Schema(
            {cv.string: cv.string},
        ),
    },
)

_LOGGER = logging.getLogger(__name__)


class PlaybookStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType
    ) -> None:
        self._hass = hass
        self._active_playbook: Playbook | None = None
        self._loaded_playbooks: dict[str, Playbook] = {}
        self._update_callback: Callable | None = None
        self._start_time: datetime | None = None
        self._cancel_timer = None
        self._config = config

    def set_update_callback(self, update_callback: Callable):
        self._update_callback = update_callback

    async def calculate(self, entity_state: State) -> Decimal | None:
        return Decimal(0)

    async def activate_playbook(self, playbook_id: str) -> None:
        _LOGGER.debug(f"Activating playbook {playbook_id}")
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
            _LOGGER.debug(f"Playbook {self._active_playbook.id} completed")
            return

        entry = queue.dequeue()

        @callback
        def _update_power(event: Event) -> None:
            _LOGGER.debug(f"playbook {self._active_playbook.id}: Update power {entry.power}")
            self._update_callback(entry.power)
            # Schedule next update
            self._execute_playbook_entry()

        # Schedule update in the future
        self._cancel_timer = async_track_point_in_time(
            self._hass,
            _update_power,
            self._start_time + timedelta(seconds=entry.time),
        )

    async def _load_playbook(self, playbook_id: str) -> Playbook:
        if playbook_id in self._loaded_playbooks:
            return self._loaded_playbooks[playbook_id]

        playbooks = self._config.get(CONF_PLAYBOOKS)
        if not playbook_id in playbooks:
            raise RuntimeError() #todo correct exception

        playbook_file = playbooks[playbook_id]


        # todo actual loading of playbooks
        queue = PlaybookQueue()
        queue.enqueue(PlaybookEntry(time=5, power=Decimal(40)))
        self._loaded_playbooks = Playbook(id=playbook_id, queue=queue)
        return self._loaded_playbooks


@dataclass
class Playbook:
    id: str
    queue: PlaybookQueue


class PlaybookQueue:
    def __init__(self) -> None:
        self._entries = deque()

    def enqueue(self, entry: PlaybookEntry) -> None:
        self._entries.append(entry)

    def dequeue(self) -> PlaybookEntry:
        return self._entries.popleft()

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class PlaybookEntry:
    time: float
    power: Decimal
