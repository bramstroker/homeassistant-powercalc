from __future__ import annotations

from measure.controller.fan.controller import FanController


class DummyFanController(FanController):
    def set_percentage(self, percentage: int) -> None:
        pass

    def turn_off(self) -> None:
        pass
