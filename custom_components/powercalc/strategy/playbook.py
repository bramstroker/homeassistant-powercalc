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

from custom_components.powercalc.const import (
    CONF_AUTOSTART,
    CONF_PLAYBOOKS,
    CONF_REPEAT,
)
from custom_components.powercalc.errors import StrategyConfigurationError

from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PLAYBOOKS): vol.Schema(
            {cv.string: cv.string},
        ),
        vol.Optional(CONF_AUTOSTART): cv.string,
        vol.Optional(CONF_REPEAT, default=False): cv.boolean,
    },
)

_LOGGER = logging.getLogger(__name__)


class PlaybookStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        playbook_directory: str | None = None,
    ) -> None:
        self._hass = hass
        self._active_playbook: Playbook | None = None
        self._loaded_playbooks: dict[str, Playbook] = {}
        self._update_callback: Callable[[Decimal], None] = lambda power: None
        self._start_time: datetime = dt.utcnow()
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._config = config
        self._repeat: bool = bool(config.get(CONF_REPEAT))
        self._autostart: str | None = config.get(CONF_AUTOSTART)
        self._power = Decimal(0)
        if not playbook_directory:
            self._playbook_directory: str = os.path.join(
                hass.config.config_dir,
                "powercalc/playbooks",
            )

    def set_update_callback(self, update_callback: Callable[[Decimal], None]) -> None:
        """
        Register update callback which allows to give the strategy instance access to the power sensor
        and manipulate the state
        """
        self._update_callback = update_callback

    async def calculate(self, entity_state: State) -> Decimal | None:
        return self._power

    async def on_start(self, hass: HomeAssistant) -> None:
        if self._autostart:
            await self.activate_playbook(self._autostart)

    async def activate_playbook(self, playbook_id: str) -> None:
        """Activate and execute a given playbook"""
        if self._active_playbook:
            await self.stop_playbook()

        _LOGGER.debug(f"Activating playbook {playbook_id}")
        playbook = await self._load_playbook(playbook_id=playbook_id)
        self._active_playbook = playbook
        self._start_time = dt.utcnow()

        self._execute_playbook_entry()

    async def stop_playbook(self) -> None:
        """Activate and execute a given playbook"""
        if not self._active_playbook:
            return

        _LOGGER.debug("Stopping playbook")
        self._active_playbook = None
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    @callback
    def _execute_playbook_entry(self) -> None:
        """Execute one step of the playbook"""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

        if not self._active_playbook:  # pragma: no cover
            _LOGGER.error("Could not execute next playbook entry. No active playbook")
            return

        queue = self._active_playbook.queue
        if len(queue) == 0:
            if self._repeat:
                _LOGGER.debug(f"Playbook {self._active_playbook.key} repeating")
                self._start_time = dt.utcnow()
                queue.reset()
                self._execute_playbook_entry()
                return

            _LOGGER.debug(f"Playbook {self._active_playbook.key} completed")
            self._active_playbook = None
            return

        entry = queue.dequeue()

        @callback
        def _update_power(date_time: datetime) -> None:
            self._power = entry.power
            _LOGGER.debug(f"playbook {self._active_playbook.key}: Update power {self._power}")  # type: ignore
            self._update_callback(self._power)
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
            raise StrategyConfigurationError(
                f"Playbook with id {playbook_id} not defined in playbooks config",
            )

        file_path = os.path.join(self._playbook_directory, playbooks[playbook_id])
        if not os.path.exists(file_path):
            raise StrategyConfigurationError(
                f"Playbook file '{file_path}' does not exist",
            )

        with open(file_path) as csv_file:
            csv_reader = csv.reader(csv_file)
            entries = []
            for row in csv_reader:
                if len(row) != 2:
                    raise StrategyConfigurationError(
                        f"Playbook file '{file_path}' has invalid structure, please see the documentation.",
                    )
                entries.append(PlaybookEntry(time=float(row[0]), power=Decimal(row[1])))

            self._loaded_playbooks[playbook_id] = Playbook(
                key=playbook_id,
                queue=PlaybookQueue(entries),
            )

        return self._loaded_playbooks[playbook_id]


class PlaybookQueue:
    def __init__(self, items: list[PlaybookEntry]) -> None:
        self._items = items
        self._queue: deque[PlaybookEntry] = deque(items)

    def dequeue(self) -> PlaybookEntry:
        return self._queue.popleft()

    def reset(self) -> None:
        self._queue = deque(self._items)

    def __len__(self) -> int:
        return len(self._queue)


@dataclass
class Playbook:
    key: str
    queue: PlaybookQueue


@dataclass
class PlaybookEntry:
    time: float
    power: Decimal
