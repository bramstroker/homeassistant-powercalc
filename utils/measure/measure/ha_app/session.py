from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Event, Lock
from typing import Any

from measure.execution import MeasurementCancelledError


class SessionState(StrEnum):
    IDLE = "idle"
    VALIDATING = "validating"
    READY = "ready"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    RESUMABLE = "resumable"


class SessionEventType(StrEnum):
    STATE = "state"
    PROGRESS = "progress"
    WARNING = "warning"
    LOG = "log"
    CHECKPOINT = "checkpoint"
    SAMPLE = "sample"


@dataclass(frozen=True)
class SessionEvent:
    sequence: int
    type: SessionEventType
    created_at: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionSnapshot:
    """Persisted projection of the current session state."""

    id: str
    state: SessionState
    created_at: str
    updated_at: str
    completed: int = 0
    total: int = 0
    mode: str | None = None
    estimated_remaining: str | None = None
    error: str | None = None
    files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    event_sequence: int = 0
    summary: dict[str, str] | None = None

    @property
    def progress(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.completed / self.total * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["progress"] = self.progress
        return data


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class SessionControl:
    """Thread-safe bridge for worker cancellation, confirmation and events."""

    initial_sequence: int = 0
    _cancelled: Event = field(default_factory=Event)
    _listeners: list[Callable[[SessionEvent], None]] = field(default_factory=list)
    _confirmed: Event = field(default_factory=Event)
    _sequence: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        self._sequence = self.initial_sequence

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def checkpoint(self) -> None:
        if self.is_cancelled:
            raise MeasurementCancelledError

    def wait(self, seconds: float) -> None:
        if seconds <= 0:
            self.checkpoint()
            return
        if self._cancelled.wait(seconds):
            raise MeasurementCancelledError

    def confirm(self, message: str) -> None:
        """Pause at an operator checkpoint while remaining cancellable."""

        self._confirmed.clear()
        self.emit(SessionEventType.CHECKPOINT, {"message": message})
        while not self._confirmed.wait(0.25):
            self.checkpoint()
        self.checkpoint()

    def continue_run(self) -> None:
        self._confirmed.set()

    def subscribe(self, listener: Callable[[SessionEvent], None]) -> None:
        self._listeners.append(listener)

    @property
    def sequence(self) -> int:
        """Return the last sequence allocated, including transient events."""
        with self._lock:
            return self._sequence

    def emit(self, event_type: SessionEventType, data: dict[str, Any]) -> SessionEvent:
        """Allocate a sequence number and notify a stable listener snapshot."""

        with self._lock:
            self._sequence += 1
            event = SessionEvent(
                sequence=self._sequence,
                type=event_type,
                created_at=utc_now(),
                data=data,
            )
        for listener in tuple(self._listeners):
            listener(event)
        return event

    def progress(self, *, completed: int, total: int, mode: str, estimated_remaining: str) -> None:
        self.emit(
            SessionEventType.PROGRESS,
            {
                "completed": completed,
                "total": total,
                "mode": mode,
                "estimated_remaining": estimated_remaining,
            },
        )

    def log(self, message: str, *, warning: bool = False) -> None:
        self.emit(SessionEventType.WARNING if warning else SessionEventType.LOG, {"message": message})

    def sample(self, power: float) -> None:
        """Emit a transient live power reading for realtime visualisation."""
        self.emit(SessionEventType.SAMPLE, {"power": round(power, 2)})
