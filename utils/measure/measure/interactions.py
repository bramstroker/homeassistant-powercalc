from __future__ import annotations

import time

from measure.session import SessionControl


class ConsoleInteraction:
    """CLI implementation of the shared execution interaction boundary."""

    def confirm(self, message: str) -> None:
        input(f"{message}\nPress enter to continue...")

    def notify(self, message: str) -> None:
        print(message)

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


class ImmediateInteraction:
    """Non-interactive adapter used when a run has no confirmation checkpoint."""

    def confirm(self, _: str) -> None:
        return

    def notify(self, _: str) -> None:
        return

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


class SessionInteraction:
    """GUI implementation backed by coordinator events and cooperative cancellation."""

    def __init__(self, control: SessionControl) -> None:
        self.control = control

    def confirm(self, message: str) -> None:
        self.control.confirm(message)

    def notify(self, message: str) -> None:
        self.control.log(message)

    def wait(self, seconds: float) -> None:
        self.control.wait(seconds)
