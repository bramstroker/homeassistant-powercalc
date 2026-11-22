from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import TrackTemplate


class PowerCalculationStrategyInterface:
    async def async_update_state(self) -> None:
        """Collect source readings, including while calculation is disabled or a composite branch is skipped."""

    def is_sample_entity(self, entity_id: str) -> bool:
        """Return whether this entity supplies readings independently of the source state.

        The default ignores entity_id because it has no independent sample entities.
        """
        return False

    def get_update_interval(self) -> timedelta | None:
        """Return the interval needed for time-dependent calculations, if any."""
        return None

    def get_next_update_time(self) -> datetime | None:
        """Return the next time a held calculation changes without a source event."""
        return None

    async def initialize(self) -> None:
        """Initialize the strategy, called once on creation."""

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate power consumption based on entity state."""

    async def calculate_on_refresh(self, entity_state: State) -> Decimal | None:
        """Refresh power after a timer or sample update."""
        return await self.calculate(entity_state)

    async def validate_config(self) -> None:
        """Validate correct setup of the strategy."""

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        """Return entities to track for this strategy."""
        return []

    def can_calculate_standby(self) -> bool:
        """Return if this strategy can calculate standby power."""
        return False

    def is_enabled(self, entity_state: State) -> bool:
        """Return if this strategy is enabled based on entity state."""
        return True

    def set_update_callback(self, update_callback: Callable[[Decimal], None]) -> None:
        """Register update callback to allow strategy to push power updates."""

    async def on_start(self, hass: HomeAssistant) -> None:
        """Called after HA has started"""
