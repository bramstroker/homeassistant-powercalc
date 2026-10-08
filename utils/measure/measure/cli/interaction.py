from collections.abc import Mapping
import time

from measure.runner.interaction import OperatingPoint, RunInteraction
from measure.start import MeasurementStart


class ConsoleInteraction(RunInteraction):
    """Interactive terminal implementation of the execution boundary."""

    def __init__(self, start: MeasurementStart | None = None) -> None:
        self.start = start

    def confirm(self, message: str, *, action: str | None = None) -> None:
        if self.start and action == self.start.action and self.start.guidance:
            steps = "\n".join(f"{index}. {step}" for index, step in enumerate(self.start.guidance, start=1))
            message = f"{message}\n\n{self.start.guidance_title}:\n{steps}"
        input(f"{message}\nPress enter to continue...")

    def notify(self, message: str) -> None:
        print(message)

    def choose(self, message: str, *, default: bool) -> bool:
        suffix = "Y/n" if default else "y/N"
        answer = input(f"{message} [{suffix}] ").strip().casefold()
        if not answer:
            return default
        return answer in {"y", "yes"}

    def phase(self, message: str) -> None:
        return

    def progress(
        self,
        completed: int,
        total: int,
        *,
        phase: str,
        remaining_seconds: float | None = None,
        skipped: int = 0,
    ) -> None:
        return

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def checkpoint(self) -> None:
        return

    def operating_point(self, point: OperatingPoint) -> None:
        return

    def entity_states(self, states: Mapping[str, str]) -> None:
        return
