from collections.abc import Mapping
import time
from typing import Literal, NotRequired, Protocol, TypedDict


class LightOperatingPoint(TypedDict):
    type: Literal["light"]
    on: bool
    brightness: NotRequired[int]
    color_temp_mired: NotRequired[int]
    hue: NotRequired[int]
    saturation: NotRequired[int]
    effect: NotRequired[str]


class SpeakerOperatingPoint(TypedDict):
    type: Literal["speaker"]
    volume: int
    muted: bool


class FanOperatingPoint(TypedDict):
    type: Literal["fan"]
    percentage: int
    on: bool


class ChargingOperatingPoint(TypedDict):
    type: Literal["charging"]
    battery_level: int
    charging: bool


type OperatingPoint = LightOperatingPoint | SpeakerOperatingPoint | FanOperatingPoint | ChargingOperatingPoint


class RunInteraction(Protocol):
    """Full interaction boundary used while a measurement is running."""

    def confirm(self, message: str, *, action: str | None = None) -> None:
        """Wait until the user confirms a physical preparation step."""

    def choose(self, message: str, *, default: bool) -> bool:
        """Request a binary runtime choice."""

    def notify(self, message: str) -> None:
        """Report information which does not represent a measurement phase."""

    def phase(self, message: str) -> None:
        """Report the current activity when numeric progress is unavailable."""

    def progress(
        self,
        completed: int,
        total: int,
        *,
        phase: str,
        remaining_seconds: float | None = None,
        skipped: int = 0,
    ) -> None:
        """Report measurement progress. ``total`` of 0 means the run is open-ended."""

    def wait(self, seconds: float) -> None:
        """Wait for a duration, raising if the run is cancelled."""

    def checkpoint(self) -> None:
        """Raise when the active run has been cancelled."""

    def operating_point(self, point: OperatingPoint) -> None:
        """Report the device state currently being measured."""

    def entity_states(self, states: Mapping[str, str]) -> None:
        """Report the latest states captured by a recorder session."""


class ImmediateInteraction(RunInteraction):
    """Non-interactive execution adapter used by tests and unattended runs."""

    def confirm(self, _: str, *, action: str | None = None) -> None:
        del action

    def notify(self, _: str) -> None:
        return

    def choose(self, _: str, *, default: bool) -> bool:
        return default

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
