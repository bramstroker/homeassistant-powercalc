from __future__ import annotations

from measure.execution import RunInteraction
from measure.ha_app.session import SessionControl


class SessionInteraction(RunInteraction):
    """Home Assistant session implementation with progress and cancellation."""

    def __init__(self, control: SessionControl) -> None:
        self.control = control

    def confirm(self, message: str) -> None:
        self.control.confirm(message)

    def notify(self, message: str) -> None:
        self.control.log(message)

    def choose(self, message: str, *, default: bool) -> bool:
        choice = "yes" if default else "no"
        self.control.log(f"{message} Using the non-interactive default: {choice}.")
        return default

    def progress(self, completed: int, total: int, *, phase: str, remaining_seconds: float | None = None) -> None:
        remaining = "" if remaining_seconds is None else f"{int(remaining_seconds)}s"
        self.control.progress(completed=completed, total=total, mode=phase, estimated_remaining=remaining)

    def wait(self, seconds: float) -> None:
        self.control.wait(seconds)

    def checkpoint(self) -> None:
        self.control.checkpoint()
