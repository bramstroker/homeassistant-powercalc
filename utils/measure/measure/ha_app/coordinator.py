from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import logging
from pathlib import Path
from threading import Lock, Thread
import time
from typing import Protocol, cast
from uuid import uuid4

from measure.clock import utc_now
from measure.execution import MeasurementCancelledError, OperatingPoint
from measure.ha_app.session import (
    ACTIVE_SESSION_STATES,
    SessionControl,
    SessionEvent,
    SessionEventType,
    SessionSnapshot,
    SessionState,
)
from measure.ha_app.storage import SessionStorage
from measure.request import MeasurementRequest, ResumePolicy
from measure.runner.runner import RunnerResult

_LOGGER = logging.getLogger("measure")
_SNAPSHOT_PERSIST_INTERVAL = 5.0


class SessionConflictError(Exception):
    """Raised when an operation conflicts with the active session state."""


@dataclass(frozen=True)
class SessionExecutionContext:
    """Explicit identity and artifact location for one session execution."""

    session_id: str
    artifact_directory: Path


class SessionMeasurementService(Protocol):
    """Run one session without exposing its adapter composition to the coordinator."""

    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        context: SessionExecutionContext,
    ) -> RunnerResult: ...


class MeasurementCoordinator:
    """Own the single persisted Home Assistant measurement session.

    State transitions are serialized under a lock while the measurement runs on a worker thread.
    """

    def __init__(self, storage: SessionStorage, service_factory: Callable[[], SessionMeasurementService]) -> None:
        self.storage = storage
        self.service_factory = service_factory
        self._lock = Lock()
        self._snapshot = storage.load_current()
        self._events = list(storage.load_events(self._snapshot.id)) if self._snapshot is not None else []
        self._last_snapshot_write = 0.0
        self._control: SessionControl | None = None
        self._worker: Thread | None = None

    @property
    def current(self) -> SessionSnapshot | None:
        with self._lock:
            return self._snapshot

    def start(self, request: MeasurementRequest) -> SessionSnapshot:
        """Persist and launch a new session, rejecting overlapping work."""

        with self._lock:
            if self._snapshot and self._snapshot.state in ACTIVE_SESSION_STATES:
                raise SessionConflictError("A measurement session is already active")
            if request.resume_policy == ResumePolicy.RESUME:
                raise SessionConflictError("Use the current-session resume action for persisted output")
            now = utc_now()
            snapshot = SessionSnapshot(
                id=str(uuid4()),
                state=SessionState.READY,
                created_at=now,
                updated_at=now,
            )
            self.storage.create(snapshot, request)
            # Bound add-on storage: keep the new session, plus the replaced one when the
            # operator chose to preserve its output instead of overwriting it.
            keep = {snapshot.id}
            if request.resume_policy != ResumePolicy.OVERWRITE and self._snapshot is not None:
                keep.add(self._snapshot.id)
            self.storage.prune_sessions(keep)
            self._snapshot = snapshot
            self._events = []
            self._last_snapshot_write = 0.0
            self._launch_locked(request)
            return self._snapshot

    def resume(self) -> SessionSnapshot:
        """Relaunch the current session from compatible persisted output."""

        with self._lock:
            if self._snapshot is None or self._snapshot.state not in {
                SessionState.RESUMABLE,
                SessionState.CANCELLED,
                SessionState.FAILED,
            }:
                raise SessionConflictError("The current session cannot be resumed")
            if not self.storage.can_resume(self._snapshot.id):
                raise SessionConflictError("The current session has no compatible complete row to resume")
            request = self.storage.load_request(self._snapshot.id).model_copy(
                update={"resume_policy": ResumePolicy.RESUME},
            )
            self._launch_locked(request)
            return self._snapshot

    def cancel(self) -> SessionSnapshot:
        """Persist cancellation intent and signal the worker cooperatively."""

        with self._lock:
            if self._snapshot is not None and self._snapshot.state == SessionState.CANCELLED:
                return self._snapshot
            if self._snapshot is None or self._snapshot.state not in {
                SessionState.RUNNING,
                SessionState.AWAITING_CONFIRMATION,
                SessionState.CANCELLING,
            }:
                raise SessionConflictError("No running measurement session")
            if self._snapshot.state != SessionState.CANCELLING:
                self._snapshot = replace(
                    self._snapshot,
                    state=SessionState.CANCELLING,
                    phase="Cancelling measurement",
                    confirmation_message=None,
                    updated_at=utc_now(),
                )
                self.storage.write_snapshot(self._snapshot)
            if self._control is not None:
                self._control.cancel()
            return self._snapshot

    def confirm(self) -> SessionSnapshot:
        """Release a worker paused at an operator checkpoint."""

        with self._lock:
            if self._snapshot is None or self._snapshot.state != SessionState.AWAITING_CONFIRMATION:
                raise SessionConflictError("The current session is not waiting for confirmation")
            if self._control is None:
                raise SessionConflictError("The current session cannot be continued")
            self._snapshot = replace(
                self._snapshot,
                state=SessionState.RUNNING,
                phase="Starting measurement",
                confirmation_message=None,
                updated_at=utc_now(),
            )
            self.storage.write_snapshot(self._snapshot)
            self._control.continue_run()
            return self._snapshot

    def events_since(self, sequence: int) -> tuple[SessionEvent, ...]:
        """Return buffered events after ``sequence`` for client replay."""

        with self._lock:
            return tuple(event for event in self._events if event.sequence > sequence)

    def _launch_locked(self, request: MeasurementRequest) -> None:
        """Create session control and launch the worker while holding the coordinator lock."""

        assert self._snapshot is not None
        self._control = SessionControl(initial_sequence=self._snapshot.event_sequence)
        self._control.subscribe(self._handle_event)
        self._snapshot = replace(
            self._snapshot,
            state=SessionState.RUNNING,
            phase="Initializing measurement",
            confirmation_message=None,
            updated_at=utc_now(),
            error=None,
        )
        self.storage.write_snapshot(self._snapshot)
        session_id = self._snapshot.id
        self._worker = Thread(
            target=self._run,
            args=(session_id, request, self._control),
            name=f"measure-{session_id[:8]}",
            daemon=True,
        )
        self._worker.start()

    def _run(
        self,
        session_id: str,
        request: MeasurementRequest,
        control: SessionControl,
    ) -> None:
        try:
            context = SessionExecutionContext(
                session_id=session_id,
                artifact_directory=self.storage.artifact_directory(session_id, request.model_id),
            )
            result = self.service_factory().run(
                request,
                control,
                context,
            )
        except MeasurementCancelledError:
            self._finish(SessionState.CANCELLED)
        except Exception as error:
            _LOGGER.exception("Measurement session %s failed", session_id)
            self._finish(SessionState.FAILED, error=str(error))
        else:
            self._finish(SessionState.COMPLETED, summary=result.summary)

    def _handle_event(self, event: SessionEvent) -> None:
        """Project runner events onto the snapshot and persistence policy."""

        with self._lock:
            if self._snapshot is None:
                return
            self._events.append(event)
            if len(self._events) > 1000:
                self._events = self._events[-1000:]
            if event.type == SessionEventType.SAMPLE:
                # High-frequency live readings: stream to clients, but don't persist
                # the snapshot. Keep the in-memory cursor current so the terminal
                # state cannot reuse a transient event's sequence number.
                self._snapshot = replace(self._snapshot, event_sequence=event.sequence, updated_at=event.created_at)
                return
            if event.type == SessionEventType.PROGRESS:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    completed=int(event.data["completed"]),
                    total=int(event.data["total"]),
                    phase=str(event.data["mode"]),
                    mode=str(event.data["mode"]),
                    estimated_remaining=str(event.data["estimated_remaining"]),
                )
            elif event.type == SessionEventType.PHASE:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    phase=str(event.data["message"]),
                )
            elif event.type == SessionEventType.OPERATING_POINT:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    operating_point=cast(OperatingPoint, event.data),
                )
            elif event.type == SessionEventType.WARNING:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    warnings=(*self._snapshot.warnings[-19:], str(event.data["message"])),
                )
            elif event.type == SessionEventType.CHECKPOINT:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    state=SessionState.AWAITING_CONFIRMATION,
                    phase="Waiting for confirmation",
                    confirmation_message=str(event.data["message"]),
                )
            else:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                )
            durable = event.type in {
                SessionEventType.STATE,
                SessionEventType.PHASE,
                SessionEventType.WARNING,
                SessionEventType.CHECKPOINT,
            }
            self.storage.append_event(self._snapshot.id, event, durable=durable)
            if self._should_persist_snapshot(event):
                self.storage.write_snapshot(self._snapshot)
                self._last_snapshot_write = time.monotonic()

    def _should_persist_snapshot(self, event: SessionEvent) -> bool:
        if event.type == SessionEventType.LOG:
            return False
        if event.type != SessionEventType.PROGRESS:
            return True
        return time.monotonic() - self._last_snapshot_write >= _SNAPSHOT_PERSIST_INTERVAL

    def _finish(self, state: SessionState, error: str | None = None, summary: dict[str, str] | None = None) -> None:
        """Persist the terminal snapshot and its final state event."""

        with self._lock:
            if self._snapshot is None:
                return
            files = self.storage.list_files(self._snapshot.id)
            updated_at = utc_now()
            sequence = (
                max(
                    self._snapshot.event_sequence,
                    self._control.sequence if self._control is not None else 0,
                )
                + 1
            )
            self._snapshot = replace(
                self._snapshot,
                state=state,
                phase={
                    SessionState.CANCELLED: "Measurement cancelled",
                    SessionState.COMPLETED: "Measurement completed",
                    SessionState.FAILED: "Measurement failed",
                }.get(state, self._snapshot.phase),
                confirmation_message=None,
                updated_at=updated_at,
                error=error,
                files=files,
                event_sequence=sequence,
                summary=summary if summary is not None else self._snapshot.summary,
            )
            event = SessionEvent(
                sequence=sequence,
                type=SessionEventType.STATE,
                created_at=updated_at,
                data={"state": state, "error": error},
            )
            self._events.append(event)
            self.storage.append_event(self._snapshot.id, event)
            self.storage.write_snapshot(self._snapshot)
