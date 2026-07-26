from __future__ import annotations

from measure.controller.fan.controller import FanController


class DummyFanController(FanController):
    def set_percentage(self, percentage: int) -> None:
        # Dummy controller intentionally performs no fan device action.
        pass

    def turn_off(self) -> None:
        # Dummy controller intentionally performs no fan device action.
        pass
