from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import logging
from pathlib import Path
from threading import Lock, Thread
from typing import Protocol
from uuid import uuid4

from measure.request import (
    LightMeasurementRequest,
    LightMeasurementRequestModel,
    MeasurementRunRequest,
    MeasurementRunRequestModel,
    ResumePolicy,
)
from measure.runner.runner import RunnerResult
from measure.session import (
    MeasurementCancelledError,
    SessionControl,
    SessionEvent,
    SessionEventType,
    SessionSnapshot,
    SessionState,
    utc_now,
)
from measure.storage import SessionStorage

_LOGGER = logging.getLogger("measure")


class SessionConflictError(Exception):
    """Raised when an operation conflicts with the active session state."""


class MeasurementExecutor(Protocol):
    def run(
        self,
        request: LightMeasurementRequest | MeasurementRunRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]: ...


class MeasurementCoordinator:
    def __init__(self, storage: SessionStorage, service_factory: Callable[[], MeasurementExecutor]) -> None:
        self.storage = storage
        self.service_factory = service_factory
        self._lock = Lock()
        self._snapshot = storage.load_current()
        self._events: list[SessionEvent] = []
        self._control: SessionControl | None = None
        self._worker: Thread | None = None

    @property
    def current(self) -> SessionSnapshot | None:
        with self._lock:
            return self._snapshot

    def start(self, request: LightMeasurementRequestModel | MeasurementRunRequestModel) -> SessionSnapshot:
        with self._lock:
            if self._snapshot and self._snapshot.state in {
                SessionState.VALIDATING,
                SessionState.READY,
                SessionState.AWAITING_CONFIRMATION,
                SessionState.RUNNING,
                SessionState.CANCELLING,
            }:
                raise SessionConflictError("A measurement session is already active")
            if request.resume_policy == ResumePolicy.RESUME:
                raise SessionConflictError("Use the current-session resume action for persisted output")
            previous_session_id = None
            if request.resume_policy == ResumePolicy.OVERWRITE and self._snapshot is not None:
                previous_session_id = self._snapshot.id
            now = utc_now()
            snapshot = SessionSnapshot(
                id=str(uuid4()),
                state=SessionState.READY,
                created_at=now,
                updated_at=now,
            )
            self.storage.create(snapshot, request)
            if previous_session_id is not None:
                self.storage.delete_session(previous_session_id)
            self._snapshot = snapshot
            self._events = []
            self._launch_locked(request)
            return self._snapshot

    def resume(self) -> SessionSnapshot:
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
                self._snapshot = replace(self._snapshot, state=SessionState.CANCELLING, updated_at=utc_now())
                self.storage.write_snapshot(self._snapshot)
            if self._control is not None:
                self._control.cancel()
            return self._snapshot

    def confirm(self) -> SessionSnapshot:
        with self._lock:
            if self._snapshot is None or self._snapshot.state != SessionState.AWAITING_CONFIRMATION:
                raise SessionConflictError("The current session is not waiting for confirmation")
            if self._control is None:
                raise SessionConflictError("The current session cannot be continued")
            self._snapshot = replace(self._snapshot, state=SessionState.RUNNING, updated_at=utc_now())
            self.storage.write_snapshot(self._snapshot)
            self._control.continue_run()
            return self._snapshot

    def events_since(self, sequence: int) -> tuple[SessionEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence > sequence)

    def _launch_locked(self, request: LightMeasurementRequestModel | MeasurementRunRequestModel) -> None:
        assert self._snapshot is not None
        self._control = SessionControl(initial_sequence=self._snapshot.event_sequence)
        self._control.subscribe(self._handle_event)
        self._snapshot = replace(self._snapshot, state=SessionState.RUNNING, updated_at=utc_now(), error=None)
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
        request: LightMeasurementRequestModel | MeasurementRunRequestModel,
        control: SessionControl,
    ) -> None:
        try:
            result, _ = self.service_factory().run(
                request.to_domain(),
                control,
                self.storage.output_directory(session_id),
            )
        except MeasurementCancelledError:
            self._finish(SessionState.CANCELLED)
        except Exception as error:
            _LOGGER.exception("Measurement session %s failed", session_id)
            self._finish(SessionState.FAILED, error=str(error))
        else:
            self._finish(SessionState.COMPLETED, summary=result.summary)

    def _handle_event(self, event: SessionEvent) -> None:
        with self._lock:
            if self._snapshot is None:
                return
            self._events.append(event)
            if len(self._events) > 1000:
                self._events = self._events[-1000:]
            if event.type == SessionEventType.SAMPLE:
                # High-frequency live readings: stream to clients, but don't persist
                # or mutate the snapshot (they are transient realtime data only).
                return
            if event.type == SessionEventType.PROGRESS:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                    completed=int(event.data["completed"]),
                    total=int(event.data["total"]),
                    mode=str(event.data["mode"]),
                    estimated_remaining=str(event.data["estimated_remaining"]),
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
                )
            else:
                self._snapshot = replace(
                    self._snapshot,
                    event_sequence=event.sequence,
                    updated_at=event.created_at,
                )
            self.storage.append_event(self._snapshot.id, event)
            self.storage.write_snapshot(self._snapshot)

    def _finish(self, state: SessionState, error: str | None = None, summary: dict[str, str] | None = None) -> None:
        with self._lock:
            if self._snapshot is None:
                return
            files = self.storage.list_files(self._snapshot.id)
            updated_at = utc_now()
            sequence = self._snapshot.event_sequence + 1
            self._snapshot = replace(
                self._snapshot,
                state=state,
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
