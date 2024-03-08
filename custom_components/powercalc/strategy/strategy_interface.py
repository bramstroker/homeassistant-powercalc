from __future__ import annotations

from decimal import Decimal

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import TrackTemplate


class PowerCalculationStrategyInterface:
    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate power consumption based on entity state."""

    async def validate_config(self) -> None:
        """Validate correct setup of the strategy."""

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        return []

    def can_calculate_standby(self) -> bool:
        return False

    async def on_start(self, hass: HomeAssistant) -> None:
        """Called after HA has started"""
