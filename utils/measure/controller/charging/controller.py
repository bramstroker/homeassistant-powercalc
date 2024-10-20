from __future__ import annotations

from typing import Any, Protocol

import inquirer.questions


class ChargingController(Protocol):
    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""
        ...

    def get_questions(self) -> list[inquirer.questions.Question]:
        """Get questions to ask for the chosen light controller"""
        ...

    def process_answers(self, answers: dict[str, Any]) -> None:
        """Process the answers of the questions"""
        ...
