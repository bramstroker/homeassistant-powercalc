from __future__ import annotations

from typing import Protocol


class ChargingController(Protocol):
    @property
    def battery_level_attribute(self) -> str | None:
        """Return the entity attribute used for profiles, or None for a sensor state."""
        ...

    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""
        ...

    def is_valid_state(self) -> bool:
        """Check if the entity is in a valid state where it is available, either charging or performing tasks"""
        ...

    def is_charging(self) -> bool:
        """Check if the device is currently charging"""
        ...
