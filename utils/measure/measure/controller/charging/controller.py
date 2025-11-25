from __future__ import annotations

from typing import Protocol

from measure.controller.answerable_protocol import Answerable


class ChargingController(Answerable, Protocol):
    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""
        ...

    def is_valid_state(self) -> bool:
        """Check if the entity is in a valid state where it is available, either charging or performing tasks"""
        ...

    def is_charging(self) -> bool:
        """Check if the device is currently charging"""
        ...
