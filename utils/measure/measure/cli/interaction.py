from collections.abc import Mapping
import time

from measure.execution import OperatingPoint, RunInteraction


class ConsoleInteraction(RunInteraction):
    """Interactive terminal implementation of the execution boundary."""

    def confirm(self, message: str, *, action: str | None = None) -> None:
        del action
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
