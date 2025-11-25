from __future__ import annotations

from typing import Any

import inquirer.questions

from measure.controller.fan.controller import FanController


class DummyFanController(FanController):
    def set_percentage(self, percentage: int) -> None:
        pass

    def turn_off(self) -> None:
        pass

    def get_questions(self) -> list[inquirer.questions.Question]:
        return []

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
