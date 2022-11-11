from __future__ import annotations

from typing import Any, NamedTuple, Protocol


class PowerMeter(Protocol):
    def get_power(self) -> PowerMeasurementResult:
        """Get a power measurement from the meter"""
        ...

    def get_questions(self) -> list[dict]:
        """Get questions to ask for the chosen powermeter"""
        ...

    def process_answers(self, answers: dict[str, Any]):
        """Process the answers to the asked questions"""
        ...


class PowerMeasurementResult(NamedTuple):
    power: float
    updated: float
