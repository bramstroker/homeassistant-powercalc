from __future__ import annotations

from collections import deque
import csv
from dataclasses import replace
import json
import logging
import math
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.ha_app.preferences import AppPreferences
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState, utc_now
from measure.request import LightMeasurementRequest, MeasurementRequest, parse_measurement_request
from measure.runner.light import CSV_HEADERS

_LOGGER = logging.getLogger("measure")


class SessionStorage:
    """Persist session state and outputs below a confined data root."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()
        self.sessions_root = self.data_root / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)

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
        self.write_snapshot(snapshot)
        self._write_json(self.data_root / "current.json", {"id": snapshot.id})
        return directory

    def delete_session(self, session_id: str) -> None:
        directory = self.session_directory(session_id)
        if directory.exists():
            shutil.rmtree(directory)

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

    def load_events(self, session_id: str, *, limit: int = 1000) -> tuple[SessionEvent, ...]:
        """Load the persisted replay window for SSE reconnections."""
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
                _LOGGER.warning("Ignoring a truncated final session event for %s", session_id)
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
        """Load the current snapshot and recover interrupted active sessions."""

        current_path = self.data_root / "current.json"
        if not current_path.exists():
            return None
        try:
            session_id = str(self._read_json(current_path)["id"])
            self.load_request(session_id)
            state_path = self.session_directory(session_id) / "state.json"
            state = self._read_json(state_path)
            snapshot = SessionSnapshot(
                id=str(state["id"]),
                state=SessionState(state["state"]),
                created_at=str(state["created_at"]),
                updated_at=str(state["updated_at"]),
                completed=int(state.get("completed", 0)),
                total=int(state.get("total", 0)),
                mode=state.get("mode"),
                estimated_remaining=state.get("estimated_remaining"),
                error=state.get("error"),
                files=tuple(state.get("files", [])),
                warnings=tuple(state.get("warnings", [])),
                event_sequence=int(state.get("event_sequence", 0)),
                summary=state.get("summary"),
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            _LOGGER.warning("Discarding incompatible current session pointer: %s", error)
            current_path.unlink(missing_ok=True)
            return None
        if snapshot.state in {
            SessionState.VALIDATING,
            SessionState.READY,
            SessionState.AWAITING_CONFIRMATION,
            SessionState.RUNNING,
            SessionState.CANCELLING,
        }:
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

    def load_request(self, session_id: str) -> MeasurementRequest:
        path = self.session_directory(session_id) / "request.json"
        return parse_measurement_request(self._read_json(path))

    def output_directory(self, session_id: str) -> Path:
        return self._contained(self.session_directory(session_id) / "output")

    def load_settings(self) -> AppPreferences:
        path = self.data_root / "settings.json"
        if not path.exists():
            return AppPreferences()
        try:
            return AppPreferences.model_validate(self._read_json(path))
        except (OSError, ValueError) as error:
            _LOGGER.warning("Could not load persisted app settings; using defaults: %s", error)
            return AppPreferences()

    def save_settings(self, settings: AppPreferences) -> AppPreferences:
        self._write_json(self.data_root / "settings.json", settings.model_dump(mode="json"))
        return settings

    def can_resume(self, session_id: str) -> bool:
        """Return whether the session has a complete row matching its persisted request."""
        try:
            request = self.load_request(session_id)
        except FileNotFoundError, KeyError, ValueError:
            return False
        if not isinstance(request, LightMeasurementRequest):
            return False
        model_root = self.output_directory(session_id) / request.model_id
        for mode in request.modes:
            path = model_root / f"{mode.value}.csv"
            if self._has_complete_measurement_row(path, CSV_HEADERS[mode], mode, request):
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
        expected_header: list[str],
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
            if len(rows) < 2 or rows[0] != expected_header:
                return False
            last_row = rows[-1]
            if len(last_row) != len(expected_header):
                return False
            if not math.isfinite(float(last_row[-1])):
                return False
            return SessionStorage._variation_matches_request(mode, last_row[:-1], request)
        except OSError, ValueError:
            return False

    @staticmethod
    def _variation_matches_request(
        mode: LutMode,
        values: list[str],
        request: LightMeasurementRequest,
    ) -> bool:
        parameters = request.parameters
        if mode == LutMode.EFFECT:
            if len(values) != 2 or not values[0].strip():
                return False
            return 1 <= int(values[1]) <= 255
        variation = [int(value) for value in values]
        if mode == LutMode.BRIGHTNESS:
            return SessionStorage._matches_inclusive_step(
                variation[0],
                1,
                255,
                parameters.resolved_bri_bri_steps,
            )
        if mode == LutMode.COLOR_TEMP:
            return (
                SessionStorage._matches_inclusive_step(
                    variation[0],
                    1,
                    255,
                    parameters.resolved_ct_bri_steps,
                )
                and MIN_MIRED <= variation[1] <= MAX_MIRED
            )
        if mode == LutMode.HS:
            return (
                SessionStorage._matches_inclusive_step(
                    variation[0],
                    1,
                    255,
                    parameters.resolved_hs_bri_steps,
                )
                and SessionStorage._matches_inclusive_step(
                    variation[1],
                    1,
                    65535,
                    parameters.resolved_hs_hue_steps,
                )
                and SessionStorage._matches_inclusive_step(
                    variation[2],
                    1,
                    255,
                    parameters.resolved_hs_sat_steps,
                )
            )
        return False

    @staticmethod
    def _matches_inclusive_step(value: int, start: int, end: int, step: int) -> bool:
        return value == end or (start <= value < end and (value - start) % step == 0)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object in {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        """Atomically replace a JSON document after flushing it to disk."""

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(value, file, indent=2, sort_keys=True, default=str)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
