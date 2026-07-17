from __future__ import annotations

from typing import Protocol


class FanController(Protocol):
    def set_percentage(self, percentage: int) -> None:
        """Set the fan to a specific percentage"""
        ...

    def turn_off(self) -> None:
        """Turn off the fan"""
        ...
