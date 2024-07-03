from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from inquirer.questions import Question


class MeasurementRunner(ABC):
    @abstractmethod
    def prepare(self, answers: dict[str, Any]) -> None: ...

    @abstractmethod
    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None: ...

    def get_questions(self) -> list[Question]:
        return []

    def measure_standby_power(self) -> float:
        return 0

    def get_export_directory(self) -> str | None:
        return None


@dataclass
class RunnerResult:
    model_json_data: dict
