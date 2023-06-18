from __future__ import annotations

import csv
import logging
import os
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt

from custom_components.powercalc.const import CONF_PLAYBOOKS
from custom_components.powercalc.errors import StrategyConfigurationError

from .strategy_interface import PowerCalculationStrategyInterface

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
        config: ConfigType,
    ) -> None:
        self._hass = hass
        self._active_playbook: Playbook | None = None
        self._loaded_playbooks: dict[str, Playbook] = {}
        self._update_callback: Callable[[Decimal], None] = lambda power: None
        self._start_time: datetime = dt.utcnow()
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._config = config

    def set_update_callback(self, update_callback: Callable[[Decimal], None]) -> None:
        """
        Register update callback which allows to give the strategy instance access to the power sensor
        and manipulate the state
        """
        self._update_callback = update_callback

    async def calculate(self, entity_state: State) -> Decimal | None:
        return Decimal(0)

    async def activate_playbook(self, playbook_id: str) -> None:
        """Activate and execute a given playbook"""
        _LOGGER.debug(f"Activating playbook {playbook_id}")
        playbook = await self._load_playbook(playbook_id=playbook_id)
        self._active_playbook = playbook
        self._start_time = dt.utcnow()

        self._execute_playbook_entry()

    @callback
    def _execute_playbook_entry(self) -> None:
        """Execute one step of the playbook"""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

        if not self._active_playbook:
            _LOGGER.error("Could not execute next playbook entry. No active playbook")
            return

        queue = self._active_playbook.queue
        if len(queue) == 0:
            _LOGGER.debug(f"Playbook {self._active_playbook.key} completed")
            self._active_playbook = None
            return

        entry = queue.dequeue()

        @callback
        def _update_power(date_time: datetime) -> None:
            _LOGGER.debug(f"playbook {self._active_playbook.key}: Update power {entry.power}")  # type: ignore
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
        """Lazy load a playbook from a CSV file"""
        if playbook_id in self._loaded_playbooks:
            return self._loaded_playbooks[playbook_id]

        playbooks: dict[str, str] = self._config.get(CONF_PLAYBOOKS)  # type: ignore
        if playbook_id not in playbooks:
            raise StrategyConfigurationError(f"Playbook with id {playbook_id} not defined in playbooks config")

        file_path = os.path.join(self._hass.config.config_dir, playbooks[playbook_id])
        if not os.path.exists(file_path):
            raise StrategyConfigurationError(f"Playbook file '{file_path}' does not exist")

        with open(file_path) as csv_file:
            queue = PlaybookQueue()

            csv_reader = csv.reader(csv_file)
            for row in csv_reader:
                queue.enqueue(PlaybookEntry(time=float(row[0]), power=Decimal(row[1])))

            self._loaded_playbooks[playbook_id] = Playbook(key=playbook_id, queue=queue)

        return self._loaded_playbooks[playbook_id]


@dataclass
class Playbook:
    key: str
    queue: PlaybookQueue


class PlaybookQueue:
    def __init__(self) -> None:
        self._entries: deque[PlaybookEntry] = deque()

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
