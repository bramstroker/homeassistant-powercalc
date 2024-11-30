from __future__ import annotations

from typing import Any, Protocol

import inquirer.questions


class ChargingController(Protocol):
    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""
        ...

    def is_valid_state(self) -> bool:
        """Check if the entity is in a valid state where it is available, either charging or performing tasks"""
        ...

    def is_charging(self) -> bool:
        """Check if the device is currently charging"""
        ...

    def get_questions(self) -> list[inquirer.questions.Question]:
        """Get questions to ask for the chosen light controller"""
        ...

    def process_answers(self, answers: dict[str, Any]) -> None:
        """Process the answers of the questions"""
        ...
