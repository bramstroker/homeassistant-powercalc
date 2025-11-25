from __future__ import annotations

from typing import Protocol

from measure.controller.answerable_protocol import Answerable


class FanController(Answerable, Protocol):
    def set_percentage(self, percentage: int) -> None:
        """Set the fan to a specific percentage"""
        ...

    def turn_off(self) -> None:
        """Turn off the fan"""
        ...
