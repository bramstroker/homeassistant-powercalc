from __future__ import annotations

from typing import Any

from .controller import LightInfo


class DummyLightController:
    def change_light_state(self, color_mode: str, on: bool = True, **kwargs):
        pass

    def get_light_info(self) -> LightInfo:
        return LightInfo("")

    def get_questions(self) -> list[dict]:
        return []

    def process_answers(self, answers: dict[str, Any]):
        pass
