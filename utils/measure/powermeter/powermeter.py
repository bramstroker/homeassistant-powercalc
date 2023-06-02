from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, NamedTuple

from inquirer.questions import Question


class PowerMeter(ABC):
    @abstractmethod
    def get_power(self) -> PowerMeasurementResult:
        """Get a power measurement from the meter"""

    def get_questions(self) -> list[Question]:
        """Get questions to ask for the chosen powermeter"""
        return []

    @abstractmethod
    def process_answers(self, answers: dict[str, Any]) -> None:
        """Process the answers to the asked questions"""


class PowerMeasurementResult(NamedTuple):
    power: float
    updated: float
