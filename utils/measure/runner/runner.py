from typing import Protocol


class MeasurementRunner(Protocol):
    def prepare(self) -> None:
        ...

    def run(self, answers: dict) -> None:
        ...

    def get_questions(self) -> list[dict]:
        ...

    def measure_standby_power(self) -> float:
        ...