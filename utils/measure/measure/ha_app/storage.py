from collections import deque
import csv
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from measure.clock import utc_now
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightInfo
from measure.dummy_load import DummyLoadCalibration
from measure.files import write_json_atomic
from measure.ha_app.contribution.models import ContributionStatus
from measure.ha_app.preferences import AppPreferences
from measure.ha_app.session import (
    ACTIVE_SESSION_STATES,
    SessionEvent,
    SessionEventType,
    SessionSnapshot,
    SessionState,
)
from measure.ha_app.shelly_credentials import ShellyCredentials, ShellyCredentialStore
from measure.request import LightMeasurementRequest, MeasurementRequest, parse_measurement_request
from measure.runner.light_plan import (
    CSV_HEADERS,
    ColorTempVariation,
    EffectVariation,
    Variation,
    build_light_plan,
    variation_from_csv_row,
)

_LOGGER = logging.getLogger("measure")

_CURRENT_SESSION_FILENAME = "current.json"
_DUMMY_LOAD_CALIBRATION_FILENAME = "dummy_load_calibration.json"
_CONTRIBUTION_STATUS_FILENAME = "contribution_status.json"
_SHELLY_CREDENTIALS_FILENAME = "shelly_credentials.json"

#: Everything reading a persisted session document can raise: the directory is gone or
#: unreadable, or the JSON no longer matches the model that wrote it. Callers treat all of
#: these the same way — the session cannot be loaded — so they are caught as one set.
SESSION_LOAD_ERRORS = (OSError, KeyError, TypeError, ValueError)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class SessionStorage:
    """Persist session state and outputs below a confined data root."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()
        self.sessions_root = self.data_root / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        # Requests are immutable per session; cache them so hot paths (SSE encoding)
        # do not re-read and re-validate the JSON document from disk.
        self._request_cache: dict[str, MeasurementRequest] = {}
        self._shelly_credentials = ShellyCredentialStore(self.data_root / _SHELLY_CREDENTIALS_FILENAME)

    def session_directory(self, session_id: str) -> Path:
        if not session_id or not session_id.replace("-", "").isalnum():
            raise ValueError("Invalid session id")
        return self._contained(self.sessions_root / session_id)

    def create(
        self,
        snapshot: SessionSnapshot,
        request: MeasurementRequest,
    ) -> Path:
        """Create a session layout and mark it as current."""

        directory = self.session_directory(snapshot.id)
        (directory / "output").mkdir(parents=True, exist_ok=False)
        self._write_json(directory / "request.json", request.model_dump(mode="json"))
        self._request_cache[snapshot.id] = request
        self.write_snapshot(snapshot)
        self._write_json(self.data_root / _CURRENT_SESSION_FILENAME, {"id": snapshot.id})
        return directory

    def set_current(self, session_id: str) -> None:
        """Point startup recovery at an existing session."""
        self.load_snapshot(session_id)
        self._write_json(self.data_root / _CURRENT_SESSION_FILENAME, {"id": session_id})

    def clear_current(self, session_id: str | None = None) -> None:
        """Remove the current pointer, optionally only when it names ``session_id``."""
        path = self.data_root / _CURRENT_SESSION_FILENAME
        if session_id is not None and path.exists():
            try:
                if str(self._read_json(path)["id"]) != session_id:
                    return
            except SESSION_LOAD_ERRORS:
                pass
        path.unlink(missing_ok=True)

    def delete_session(self, session_id: str) -> None:
        self._request_cache.pop(session_id, None)
        directory = self.session_directory(session_id)
        if directory.exists():
            shutil.rmtree(directory)
        self.clear_current(session_id)

    def write_snapshot(self, snapshot: SessionSnapshot) -> None:
        directory = self.session_directory(snapshot.id)
        directory.mkdir(parents=True, exist_ok=True)
        self._write_json(directory / "state.json", snapshot.to_dict())

    def append_event(self, session_id: str, event: SessionEvent, *, durable: bool = True) -> None:
        """Append an event, fsyncing only when durability is required."""

        path = self.session_directory(session_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.to_dict(), separators=(",", ":"), default=str) + "\n")
            file.flush()
            if durable:
                os.fsync(file.fileno())

    def load_events(self, session_id: str, *, limit: int | None = 1000) -> tuple[SessionEvent, ...]:
        """Load persisted events, optionally retaining only the newest entries."""
        path = self.session_directory(session_id) / "events.jsonl"
        if not path.exists():
            return ()
        events: deque[SessionEvent] = deque(maxlen=limit)
        pending_line: str | None = None
        with path.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                if pending_line is not None:
                    events.append(self._decode_event(pending_line))
                pending_line = line
        if pending_line is not None:
            try:
                events.append(self._decode_event(pending_line))
            except json.JSONDecodeError:
                # The session id is caller-supplied, so keep it out of the log and report the
                # recovered count instead — it says as much about where the file was cut off.
                _LOGGER.warning("Ignoring a truncated final session event after %d recovered events", len(events))
        return tuple(events)

    @staticmethod
    def _decode_event(line: str) -> SessionEvent:
        value = json.loads(line)
        data = value.get("data") if isinstance(value, dict) else None
        if not isinstance(value, dict) or not isinstance(data, dict):
            raise ValueError("Persisted session event must be an object")
        return SessionEvent(
            sequence=int(value["sequence"]),
            type=SessionEventType(value["type"]),
            created_at=str(value["created_at"]),
            data=data,
        )

    def load_current(self) -> SessionSnapshot | None:
        """Load the current snapshot and recover an interrupted active session."""
        current_path = self.data_root / _CURRENT_SESSION_FILENAME
        if not current_path.exists():
            return None
        try:
            session_id = str(self._read_json(current_path)["id"])
            snapshot = self.load_snapshot(session_id)
        except SESSION_LOAD_ERRORS as error:
            _LOGGER.warning("Discarding incompatible current session pointer: %s", error)
            current_path.unlink(missing_ok=True)
            return None
        if snapshot.state in ACTIVE_SESSION_STATES:
            resumable = self.can_resume(snapshot.id)
            snapshot = replace(
                snapshot,
                state=SessionState.RESUMABLE if resumable else SessionState.FAILED,
                updated_at=utc_now(),
                error=(
                    "App stopped during measurement; compatible output can be resumed"
                    if resumable
                    else "App stopped before a compatible complete measurement row was persisted"
                ),
            )
            self.write_snapshot(snapshot)
        return snapshot

    def load_snapshot(self, session_id: str) -> SessionSnapshot:
        """Load one persisted session without changing the current pointer."""
        self.load_request(session_id)
        state = self._read_json(self.session_directory(session_id) / "state.json")
        snapshot = SessionSnapshot(
            id=str(state["id"]),
            state=SessionState(state["state"]),
            created_at=str(state["created_at"]),
            updated_at=str(state["updated_at"]),
            completed=int(state.get("completed", 0)),
            total=int(state.get("total", 0)),
            skipped=int(state.get("skipped", 0)),
            phase=state.get("phase"),
            confirmation_message=state.get("confirmation_message"),
            confirmation_action=state.get("confirmation_action"),
            mode=state.get("mode"),
            estimated_remaining=state.get("estimated_remaining"),
            error=state.get("error"),
            files=tuple(state.get("files", [])),
            warnings=tuple(state.get("warnings", [])),
            event_sequence=int(state.get("event_sequence", 0)),
            summary=state.get("summary"),
            operating_point=state.get("operating_point"),
            calibration_sample=state.get("calibration_sample"),
        )
        if snapshot.id != session_id:
            raise ValueError("Session state id does not match its directory")
        return snapshot

    def list_sessions(self) -> tuple[SessionSnapshot, ...]:
        """Return valid persisted sessions, newest activity first."""
        sessions: list[SessionSnapshot] = []
        for path in self.sessions_root.iterdir():
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                sessions.append(self.load_snapshot(path.name))
            except SESSION_LOAD_ERRORS as error:
                _LOGGER.warning("Ignoring incompatible measurement session %s: %s", path.name, error)
        return tuple(sorted(sessions, key=lambda item: item.updated_at, reverse=True))

    def session_size(self, session_id: str) -> int:
        """Return the total size of regular files stored for one session."""
        directory = self.session_directory(session_id)
        if not directory.exists():
            raise FileNotFoundError(session_id)
        return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file() and not path.is_symlink())

    def load_request(self, session_id: str) -> MeasurementRequest:
        cached = self._request_cache.get(session_id)
        if cached is not None:
            return cached
        path = self.session_directory(session_id) / "request.json"
        request = parse_measurement_request(self._read_json(path))
        self._request_cache[session_id] = request
        return request

    def output_directory(self, session_id: str) -> Path:
        return self._contained(self.session_directory(session_id) / "output")

    def artifact_directory(self, session_id: str, model_id: str) -> Path:
        """Return the confined output directory for one session model."""

        return self._contained(self.output_directory(session_id) / model_id)

    def load_settings(self) -> AppPreferences:
        path = self.data_root / "settings.json"
        settings = self._load_model(path, AppPreferences, "persisted app settings; using defaults")
        return settings if settings is not None else AppPreferences()

    def save_settings(self, settings: AppPreferences) -> AppPreferences:
        self._write_json(self.data_root / "settings.json", settings.model_dump(mode="json"))
        return settings

    def load_shelly_credentials(self) -> ShellyCredentials | None:
        try:
            return self._shelly_credentials.load()
        except (OSError, ValueError) as error:
            _LOGGER.warning("Could not load persisted Shelly credentials: %s", error)
            return None

    def save_shelly_credentials(self, credentials: ShellyCredentials) -> None:
        self._shelly_credentials.save(credentials)

    def clear_shelly_credentials(self) -> None:
        self._shelly_credentials.clear()

    def load_dummy_load_calibration(self) -> DummyLoadCalibration | None:
        return self._load_model(
            self.data_root / _DUMMY_LOAD_CALIBRATION_FILENAME,
            DummyLoadCalibration,
            "dummy-load calibration",
        )

    def save_dummy_load_calibration(self, calibration: DummyLoadCalibration) -> DummyLoadCalibration:
        self._write_json(
            self.data_root / _DUMMY_LOAD_CALIBRATION_FILENAME,
            calibration.model_dump(mode="json"),
        )
        return calibration

    def load_session_dummy_load_calibration(self, session_id: str) -> DummyLoadCalibration | None:
        return self._load_model(
            self.session_directory(session_id) / _DUMMY_LOAD_CALIBRATION_FILENAME,
            DummyLoadCalibration,
            f"session dummy-load calibration for {session_id}",
        )

    def save_session_dummy_load_calibration(
        self,
        session_id: str,
        calibration: DummyLoadCalibration,
    ) -> DummyLoadCalibration:
        self._write_json(
            self.session_directory(session_id) / _DUMMY_LOAD_CALIBRATION_FILENAME,
            calibration.model_dump(mode="json"),
        )
        return calibration

    def load_contribution_status(self) -> ContributionStatus:
        path = self.data_root / _CONTRIBUTION_STATUS_FILENAME
        status = self._load_model(path, ContributionStatus, "contribution status")
        return status if status is not None else ContributionStatus()

    def save_contribution_status(self, status: ContributionStatus) -> None:
        self._write_json(self.data_root / _CONTRIBUTION_STATUS_FILENAME, status.model_dump(mode="json"))

    def can_resume(self, session_id: str) -> bool:
        """Return whether the session has a complete row matching its persisted request."""
        try:
            request = self.load_request(session_id)
        except SESSION_LOAD_ERRORS:
            return False
        if not isinstance(request, LightMeasurementRequest):
            return False
        model_root = self.artifact_directory(session_id, request.model_id)
        for mode in request.modes:
            path = model_root / f"{mode.value}.csv"
            if self._has_complete_measurement_row(path, mode, request):
                return True
        return False

    def verify_writable(self) -> None:
        """Exercise the same create/fsync/remove operations used by session persistence."""
        probe = self._contained(self.data_root / f".write-probe-{uuid4().hex}")
        try:
            with probe.open("x", encoding="utf-8") as file:
                file.write("ok")
                file.flush()
                os.fsync(file.fileno())
        finally:
            probe.unlink(missing_ok=True)

    def list_files(self, session_id: str) -> tuple[str, ...]:
        output = self.output_directory(session_id)
        if not output.exists():
            return ()
        return tuple(
            sorted(
                str(path.relative_to(output)) for path in output.rglob("*") if path.is_file() and not path.is_symlink()
            ),
        )

    def file_path(self, session_id: str, relative_name: str) -> Path:
        """Resolve a listed regular output file without allowing path traversal."""

        output = self.output_directory(session_id)
        path = self._contained(output / relative_name)
        if not path.is_relative_to(output):
            raise ValueError("Path escapes session output directory")
        if relative_name not in self.list_files(session_id):
            raise FileNotFoundError(relative_name)
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(relative_name)
        return path

    def _contained(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.data_root):
            raise ValueError("Path escapes data root")
        return resolved

    @staticmethod
    def _has_complete_measurement_row(
        path: Path,
        mode: LutMode,
        request: LightMeasurementRequest,
    ) -> bool:
        if not path.is_file() or path.is_symlink():
            return False
        try:
            raw = path.read_bytes()
            if not raw.endswith((b"\n", b"\r")):
                return False
            rows = list(csv.reader(raw.decode("utf-8").splitlines()))
            if len(rows) < 2 or rows[0] != CSV_HEADERS[mode]:
                return False
            variation = variation_from_csv_row(rows[-1], mode)
            if variation is None:
                return False
            return SessionStorage._variation_matches_request(variation, mode, request)
        except OSError, ValueError:
            return False

    @staticmethod
    def _variation_matches_request(
        variation: Variation,
        mode: LutMode,
        request: LightMeasurementRequest,
    ) -> bool:
        """Check the parsed row against the exact plan the runner would rebuild on resume."""
        light_info = LightInfo("unknown", min_mired=MIN_MIRED, max_mired=MAX_MIRED)
        effects = [variation.effect] if isinstance(variation, EffectVariation) else ()
        plan_variations = build_light_plan({mode}, request.parameters, light_info, effects).for_mode(mode).variations
        if isinstance(variation, ColorTempVariation):
            # The light's real mired range is unknown offline, so only the brightness
            # column can be validated against the plan.
            return variation.bri in {row.bri for row in plan_variations} and MIN_MIRED <= variation.ct <= MAX_MIRED
        return variation in plan_variations

    def _load_model(self, path: Path, model: type[_ModelT], description: str) -> _ModelT | None:
        """Load one optional JSON document, treating an unreadable or outdated file as absent."""

        if not path.exists():
            return None
        try:
            return model.model_validate(self._read_json(path))
        except (OSError, ValueError) as error:
            _LOGGER.warning("Ignoring invalid %s: %s", description, error)
            return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object in {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        write_json_atomic(path, value)
