from __future__ import annotations

from typing import Any, Protocol

from .const import MAX_MIRED, MIN_MIRED


class LightInfo:
    model_id: str

    def __init__(
        self, model_id: str, min_mired: int = MIN_MIRED, max_mired: int = MAX_MIRED
    ):
        self.model_id = model_id
        self._min_mired = min_mired
        self._max_mired = max_mired

    def get_min_mired(self) -> int:
        return self._min_mired

    def set_min_mired(self, value: int):
        if value < MIN_MIRED:
            value = MIN_MIRED
        self._min_mired = value

    def get_max_mired(self) -> int:
        return self._max_mired

    def set_max_mired(self, value: int):
        if value > MAX_MIRED:
            value = MAX_MIRED
        self._max_mired = value

    min_mired = property(get_min_mired, set_min_mired)
    max_mired = property(get_max_mired, set_max_mired)


class LightController(Protocol):
    def change_light_state(self, color_mode: str, on: bool = True, **kwargs):
        """Changes the light to a certain setting"""
        ...

    def get_light_info(self) -> LightInfo:
        """Get device information about the light"""
        ...

    def get_questions(self) -> list[dict]:
        """Get questions to ask for the chosen light controller"""
        ...

    def process_answers(self, answers: dict[str, Any]):
        """Process the answers of the questions"""
        ...
