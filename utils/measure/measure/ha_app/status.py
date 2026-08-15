"""Publish Measure app presence and session state to Home Assistant."""

import asyncio
from collections.abc import Callable
import contextlib
import logging

from measure.const import HASS_EVENT_MEASURE_STATUS
from measure.ha_app.coordinator import MeasurementCoordinator
from measure.ha_app.session import SessionState
from measure.home_assistant import HomeAssistantManager
from measure.version import measure_version

_LOGGER = logging.getLogger("measure")
STATUS_HEARTBEAT_INTERVAL = 60.0


class MeasureStatusPublisher:
    """Push a retained session snapshot and periodic presence heartbeat to Home Assistant."""

    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        coordinator: MeasurementCoordinator,
        *,
        heartbeat_interval: float = STATUS_HEARTBEAT_INTERVAL,
    ) -> None:
        self._home_assistant = home_assistant
        self._coordinator = coordinator
        self._heartbeat_interval = heartbeat_interval
        self._changed = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._stopping = False

    async def async_start(self) -> None:
        """Subscribe to session transitions and publish the initial app presence."""
        self._loop = asyncio.get_running_loop()
        self._unsubscribe = self._coordinator.subscribe(self._signal_changed)
        self._changed.set()
        self._task = asyncio.create_task(self._run(), name="measure-status-publisher")

    async def async_stop(self) -> None:
        """Stop publishing and release the coordinator subscription."""
        self._stopping = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._changed.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._loop = None

    def _signal_changed(self) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._changed.set)

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._changed.wait(), timeout=self._heartbeat_interval)
            self._changed.clear()
            if self._stopping:
                return
            try:
                await asyncio.to_thread(self._publish)
            except Exception as error:  # noqa: BLE001 - presence reporting must not stop the app
                _LOGGER.warning("Could not publish Measure status to Home Assistant: %s", error)

    def _publish(self) -> None:
        snapshot = self._coordinator.current
        self._home_assistant.fire_event(
            HASS_EVENT_MEASURE_STATUS,
            app_version=measure_version(),
            state=snapshot.state if snapshot is not None else SessionState.IDLE,
            session_id=snapshot.id if snapshot is not None else None,
            error=snapshot.error if snapshot is not None else None,
        )
