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
    RESUMABLE_SESSION_STATES,
    CalibrationSample,
    SessionControl,
    SessionEvent,
    SessionEventType,
    SessionSnapshot,
    SessionState,
)
from measure.ha_app.storage import SESSION_LOAD_ERRORS, SessionStorage
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
    """Own the Home Assistant measurement sessions and the single slot they compete for.

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
        self._listeners: list[Callable[[], None]] = []

    @property
    def current(self) -> SessionSnapshot | None:
        with self._lock:
            return self._snapshot

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Notify a listener whenever the externally visible session state changes."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _notify_listeners(self) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:  # Observers must not affect measurement execution.
                _LOGGER.exception("Measurement session state listener failed")

    def get(self, session_id: str) -> SessionSnapshot:
        """Return the live projection or a stored historical snapshot."""
        with self._lock:
            return self._snapshot_locked(session_id)

    def _snapshot_locked(self, session_id: str) -> SessionSnapshot:
        """Resolve one session against the live projection first. Call while holding the lock."""

        if self._snapshot is not None and self._snapshot.id == session_id:
            return self._snapshot
        return self.storage.load_snapshot(session_id)

    def sessions(self) -> tuple[SessionSnapshot, ...]:
        """Return all retained sessions with the live projection substituted."""
        stored = self.storage.list_sessions()
        with self._lock:
            current = self._snapshot
            if current is None:
                return stored
            return tuple(current if snapshot.id == current.id else snapshot for snapshot in stored)

    def start(self, request: MeasurementRequest) -> SessionSnapshot:
        """Persist and launch a new session, rejecting overlapping work."""

        with self._lock:
            if self._snapshot and self._snapshot.state in ACTIVE_SESSION_STATES:
                raise SessionConflictError("A measurement session is already active")
            if request.resume_policy == ResumePolicy.RESUME:
                raise SessionConflictError("Use the resume action for persisted output")
            now = utc_now()
            snapshot = SessionSnapshot(
                id=str(uuid4()),
                state=SessionState.READY,
                created_at=now,
                updated_at=now,
            )
            self.storage.create(snapshot, request)
            self._snapshot = snapshot
            self._events = []
            self._last_snapshot_write = 0.0
            self._launch_locked(request)
            snapshot = self._snapshot
        self._notify_listeners()
        return snapshot

    def resume(self, session_id: str) -> SessionSnapshot:
        """Relaunch a retained session from compatible persisted output."""

        with self._lock:
            if self._snapshot is not None and self._snapshot.state in ACTIVE_SESSION_STATES:
                raise SessionConflictError("A measurement session is already active")
            try:
                snapshot = self._snapshot_locked(session_id)
            except SESSION_LOAD_ERRORS as error:
                raise SessionConflictError("The requested session does not exist") from error
            if snapshot.state not in RESUMABLE_SESSION_STATES:
                raise SessionConflictError("The requested session cannot be resumed")
            if not self.storage.can_resume(snapshot.id):
                raise SessionConflictError("The requested session has no compatible complete row to resume")
            self._snapshot = snapshot
            self._events = list(self.storage.load_events(snapshot.id))
            self.storage.set_current(snapshot.id)
            request = self.storage.load_request(snapshot.id).model_copy(
                update={"resume_policy": ResumePolicy.RESUME},
            )
            self._launch_locked(request)
            current = self._snapshot
        self._notify_listeners()
        return current

    def cancel(self, session_id: str) -> SessionSnapshot:
        """Persist cancellation intent and signal the worker cooperatively."""

        with self._lock:
            snapshot = self._require_active(session_id)
            if snapshot.state == SessionState.CANCELLED:
                return snapshot
            if snapshot.state not in {
                SessionState.RUNNING,
                SessionState.AWAITING_CONFIRMATION,
                SessionState.CANCELLING,
            }:
                raise SessionConflictError("No running measurement session")
            if snapshot.state != SessionState.CANCELLING:
                snapshot = replace(
                    snapshot,
                    state=SessionState.CANCELLING,
                    phase="Cancelling measurement",
                    confirmation_message=None,
                    confirmation_action=None,
                    updated_at=utc_now(),
                )
                self._snapshot = snapshot
                self.storage.write_snapshot(snapshot)
            if self._control is not None:
                self._control.cancel()
        self._notify_listeners()
        return snapshot

    def confirm(self, session_id: str) -> SessionSnapshot:
        """Release a worker paused at an operator checkpoint."""

        with self._lock:
            snapshot = self._require_active(session_id)
            if snapshot.state != SessionState.AWAITING_CONFIRMATION:
                raise SessionConflictError("The requested session is not waiting for confirmation")
            if self._control is None:
                raise SessionConflictError("The requested session cannot be continued")
            running: SessionSnapshot = replace(
                snapshot,
                state=SessionState.RUNNING,
                phase="Starting measurement",
                confirmation_message=None,
                confirmation_action=None,
                updated_at=utc_now(),
            )
            self._snapshot = running
            self.storage.write_snapshot(running)
            self._control.continue_run()
        self._notify_listeners()
        return running

    def delete(self, session_id: str) -> None:
        """Delete a terminal retained session."""
        with self._lock:
            try:
                snapshot = self._snapshot_locked(session_id)
            except SESSION_LOAD_ERRORS as error:
                raise SessionConflictError("The requested session does not exist") from error
            if snapshot.state in ACTIVE_SESSION_STATES:
                raise SessionConflictError("An active measurement session cannot be deleted")
            self.storage.delete_session(session_id)
            if self._snapshot is not None and self._snapshot.id == session_id:
                self._snapshot = None
                self._events = []
        self._notify_listeners()

    def _require_active(self, session_id: str) -> SessionSnapshot:
        """Return the live projection, refusing any session that does not hold the measurement slot."""

        if self._snapshot is None or self._snapshot.id != session_id:
            raise SessionConflictError("The requested session is not active")
        return self._snapshot

    def events_since(self, sequence: int, session_id: str) -> tuple[SessionEvent, ...]:
        """Return events after ``sequence`` for a live or retained session."""
        with self._lock:
            if self._snapshot is not None and self._snapshot.id == session_id:
                return tuple(event for event in self._events if event.sequence > sequence)
        return tuple(event for event in self.storage.load_events(session_id) if event.sequence > sequence)

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
            confirmation_action=None,
            calibration_sample=None,
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
            if self._project_transient_sample(event):
                return
            if event.type == SessionEventType.PROGRESS:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    completed=int(event.data["completed"]),
                    total=int(event.data["total"]),
                    skipped=int(event.data.get("skipped", 0)),
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
                    confirmation_action=(str(event.data["action"]) if event.data.get("action") else None),
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
        self._notify_checkpoint(event)

    def _notify_checkpoint(self, event: SessionEvent) -> None:
        """Publish the state transition caused by an operator checkpoint."""
        if event.type == SessionEventType.CHECKPOINT:
            self._notify_listeners()

    def _project_transient_sample(self, event: SessionEvent) -> bool:
        """Project live readings in memory without writing high-frequency snapshots."""

        assert self._snapshot is not None
        if event.type == SessionEventType.SAMPLE:
            self._snapshot = replace(self._snapshot, event_sequence=event.sequence, updated_at=event.created_at)
        elif event.type == SessionEventType.CALIBRATION_SAMPLE:
            self._snapshot = replace(
                self._snapshot,
                event_sequence=event.sequence,
                updated_at=event.created_at,
                calibration_sample=cast(CalibrationSample, event.data),
            )
        elif event.type == SessionEventType.ENTITY_STATES:
            self._snapshot = replace(
                self._snapshot,
                event_sequence=event.sequence,
                updated_at=event.created_at,
                entity_states={str(key): str(value) for key, value in event.data.get("states", {}).items()},
            )
        else:
            return False
        return True

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
                confirmation_action=None,
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
        self._notify_listeners()
