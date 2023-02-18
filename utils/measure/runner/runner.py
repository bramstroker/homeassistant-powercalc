from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from inquirer.questions import Question


class MeasurementRunner(Protocol):
    def prepare(self, answers: dict[str, Any]) -> None:
        ...

    def run(
        self, answers: dict[str, Any], export_directory: str
    ) -> RunnerResult | None:
        ...

    def get_questions(self) -> list[Question]:
        ...

    def measure_standby_power(self) -> float:
        ...

    def get_export_directory(self) -> str:
        ...


@dataclass
class RunnerResult:
    model_json_data: dict
