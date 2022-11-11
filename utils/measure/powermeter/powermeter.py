from __future__ import annotations

from typing import Any, NamedTuple
from abc import ABC, abstractmethod


class PowerMeter(ABC):
    @abstractmethod
    def get_power(self) -> PowerMeasurementResult:
        """Get a power measurement from the meter"""
        pass

    def get_questions(self) -> list[dict]:
        """Get questions to ask for the chosen powermeter"""
        return []

    def process_answers(self, answers: dict[str, Any]) -> None:
        """Process the answers to the asked questions"""
        pass


class PowerMeasurementResult(NamedTuple):
    power: float
    updated: float
