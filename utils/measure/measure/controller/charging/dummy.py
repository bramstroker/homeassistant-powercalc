from __future__ import annotations

from measure.controller.charging.controller import ChargingController


class DummyChargingController(ChargingController):
    def __init__(self) -> None:
        self._battery_level = 0

    def get_battery_level(self) -> int:
        self._battery_level += 1
        return self._battery_level - 1

    def is_valid_state(self) -> bool:
        return True

    def is_charging(self) -> bool:
        return True
