from __future__ import annotations

from typing import Any

import inquirer.questions

from .controller import ChargingController


class DummyChargingController(ChargingController):
    def get_battery_level(self) -> int:
        return 0

    def is_charging(self) -> bool:
        return True

    def get_questions(self) -> list[inquirer.questions.Question]:
        return []

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
