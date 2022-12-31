from __future__ import annotations

from typing import Any

import inquirer.questions

from .controller import LightInfo


class DummyLightController:
    def change_light_state(self, color_mode: str, on: bool = True, **kwargs):
        pass

    def get_light_info(self) -> LightInfo:
        return LightInfo("dummy")

    def get_questions(self) -> list[inquirer.questions.Question]:
        return []

    def process_answers(self, answers: dict[str, Any]):
        pass
