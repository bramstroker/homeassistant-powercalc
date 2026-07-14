from __future__ import annotations

import time

from measure.execution import RunInteraction


class ConsoleInteraction(RunInteraction):
    """Interactive terminal implementation of the execution boundary."""

    def confirm(self, message: str) -> None:
        input(f"{message}\nPress enter to continue...")

    def notify(self, message: str) -> None:
        print(message)

    def choose(self, message: str, *, default: bool) -> bool:
        suffix = "Y/n" if default else "y/N"
        answer = input(f"{message} [{suffix}] ").strip().casefold()
        if not answer:
            return default
        return answer in {"y", "yes"}

    def progress(self, completed: int, total: int, *, phase: str, remaining_seconds: float | None = None) -> None:
        return

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def checkpoint(self) -> None:
        return
