from __future__ import annotations

from typing import Any

import inquirer.questions

from .controller import ChargingController


class DummyChargingController(ChargingController):
    def __init__(self) -> None:
        self._battery_level = 0

    def get_battery_level(self) -> int:
        self._battery_level += 1
        return self._battery_level - 1

    def is_charging(self) -> bool:
        return self._battery_level <= 100

    def get_questions(self) -> list[inquirer.questions.Question]:
        return []

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
