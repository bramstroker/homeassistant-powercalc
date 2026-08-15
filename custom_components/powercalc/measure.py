"""Discovery and shared state for the Powercalc Measure app."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType

from .const import DISCOVERY_TYPE, DOMAIN, PowercalcDiscoveryType

MEASURE_STATUS_EVENT = "powercalc_measure_status"
MEASURE_STATUS_TIMEOUT = 150
MEASURE_SESSION_STATES = (
    "idle",
    "validating",
    "ready",
    "awaiting_confirmation",
    "running",
    "cancelling",
    "cancelled",
    "completed",
    "failed",
    "resumable",
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeasureStatus:
    """Sanitized status snapshot received from the Measure app."""

    app_version: str
    state: str
    session_id: str | None
    error: str | None


class MeasureAppCoordinator:
    """Track Measure app discovery, status, and heartbeat availability."""

    def __init__(self, hass: HomeAssistant, config: ConfigType) -> None:
        self.hass = hass
        self._config = config
        self.data: MeasureStatus | None = None
        self.available = False
        self.entity_creation_started = False
        self._listeners: set[Callable[[], None]] = set()
        self._cancel_stale_timer: Callable[[], None] | None = None

    @callback
    def async_setup(self) -> None:
        """Subscribe to Measure app status and Home Assistant shutdown events."""
        self.hass.bus.async_listen(MEASURE_STATUS_EVENT, self.async_handle_app_status_event)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.async_shutdown)

    async def async_handle_app_status_event(self, event: Event[dict[str, Any]]) -> None:
        """Process an app status update and set up its sensor when first detected."""
        if not self.async_process_event(event.data):
            return
        if self.entity_creation_started:
            return
        self.entity_creation_started = True
        try:
            await async_load_platform(
                self.hass,
                Platform.SENSOR,
                DOMAIN,
                {DISCOVERY_TYPE: PowercalcDiscoveryType.MEASURE_APP},
                self._config,
            )
        except Exception:
            self.entity_creation_started = False
            raise

    @callback
    def async_process_event(self, event_data: Mapping[str, Any]) -> bool:
        """Validate and store one app status event."""
        state = event_data.get("state")
        app_version = event_data.get("app_version")
        session_id = event_data.get("session_id")
        error = event_data.get("error")
        if (
            state not in MEASURE_SESSION_STATES
            or not isinstance(app_version, str)
            or (session_id is not None and not isinstance(session_id, str))
            or (error is not None and not isinstance(error, str))
        ):
            _LOGGER.debug("Ignoring invalid Powercalc Measure status event: %s", event_data)
            return False

        self.data = MeasureStatus(
            app_version=app_version,
            state=str(state),
            session_id=session_id,
            error=error,
        )
        self.available = True
        if self._cancel_stale_timer is not None:
            self._cancel_stale_timer()
        self._cancel_stale_timer = async_call_later(
            self.hass,
            MEASURE_STATUS_TIMEOUT,
            self._async_mark_unavailable,
        )
        self._async_notify_listeners()
        return True

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe an entity to status and availability updates."""
        self._listeners.add(listener)

        @callback
        def unsubscribe() -> None:
            self._listeners.discard(listener)

        return unsubscribe

    @callback
    def _async_mark_unavailable(self, _now: datetime) -> None:
        self._cancel_stale_timer = None
        self.available = False
        self._async_notify_listeners()

    @callback
    def _async_notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def async_shutdown(self, _event: Event[Any] | None = None) -> None:
        """Cancel the outstanding heartbeat timer during Home Assistant shutdown."""
        if self._cancel_stale_timer is not None:
            self._cancel_stale_timer()
            self._cancel_stale_timer = None
        self._listeners.clear()
