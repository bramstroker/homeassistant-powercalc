from __future__ import annotations

from typing import Any, Protocol

import inquirer.questions

from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode


class LightInfo:
    model_id: str

    def __init__(
        self,
        model_id: str,
        min_mired: int = MIN_MIRED,
        max_mired: int = MAX_MIRED,
    ) -> None:
        self.model_id = model_id
        self._min_mired = min_mired
        self._max_mired = max_mired

    def get_min_mired(self) -> int:
        return self._min_mired

    def set_min_mired(self, value: int) -> None:
        if value < MIN_MIRED:
            value = MIN_MIRED
        self._min_mired = value

    def get_max_mired(self) -> int:
        return self._max_mired

    def set_max_mired(self, value: int) -> None:
        if value > MAX_MIRED:
            value = MAX_MIRED
        self._max_mired = value

    min_mired = property(get_min_mired, set_min_mired)
    max_mired = property(get_max_mired, set_max_mired)


class LightController(Protocol):
    def change_light_state(self, lut_mode: LutMode, on: bool = True, **kwargs: Any) -> None:  # noqa: ANN401
        """Changes the light to a certain setting"""
        ...

    def get_light_info(self) -> LightInfo:
        """Get device information about the light"""
        ...

    def get_questions(self) -> list[inquirer.questions.Question]:
        """Get questions to ask for the chosen light controller"""
        ...

    def process_answers(self, answers: dict[str, Any]) -> None:
        """Process the answers of the questions"""
        ...

    def has_effect_support(self) -> bool:
        """Check if the light controller supports effects"""
        ...

    def get_effect_list(self) -> list[str]:
        """Get the list of supported effects"""
        ...
