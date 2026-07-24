from __future__ import annotations

from collections.abc import Collection, Iterable
import platform

from measure.clock import utc_now
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot
from measure.request import MeasurementRequest
from measure.version import measure_version

REDACTED = "<redacted>"
DIAGNOSTIC_EVENT_LIMIT = 1000
_SENSITIVE_KEYS = frozenset({"password", "secret", "token"})
_SENSITIVE_SUFFIXES = ("_ip", "_key", "_password", "_secret", "_token")
_LOG_EVENT_TYPES = frozenset({SessionEventType.LOG, SessionEventType.WARNING, SessionEventType.CHECKPOINT})


def build_session_diagnostics(
    snapshot: SessionSnapshot,
    request: MeasurementRequest,
    events: Collection[SessionEvent],
    files: Collection[dict[str, object]],
    *,
    events_truncated: bool = False,
) -> dict[str, object]:
    """Build a shareable session report without credentials or network addresses."""

    request_data = request.model_dump(mode="json")
    snapshot_data = snapshot.to_dict()
    event_data = [event.to_dict() for event in events]
    file_data = list(files)
    sensitive_values = _collect_sensitive_values([request_data, snapshot_data, event_data, file_data])
    return {
        "diagnostics_version": 1,
        "generated_at": utc_now(),
        "measure_version": _measure_version(),
        "runtime": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "snapshot": _redact(snapshot_data, sensitive_values),
        "request": _redact(request_data, sensitive_values),
        "logs": _redact(
            [event for event in event_data if SessionEventType(event["type"]) in _LOG_EVENT_TYPES],
            sensitive_values,
        ),
        "events": _redact(event_data, sensitive_values),
        "events_truncated": events_truncated,
        "event_limit": DIAGNOSTIC_EVENT_LIMIT,
        "files": _redact(file_data, sensitive_values),
        "privacy": {
            "redacted": True,
            "note": (
                "Credentials, keys, and network addresses are removed. Review device and model names before sharing."
            ),
        },
    }


def _measure_version() -> str:
    try:
        return measure_version()
    except OSError:
        return "unknown"


def _collect_sensitive_values(value: object) -> tuple[str, ...]:
    collected: set[str] = set()

    def collect(current: object) -> None:
        if isinstance(current, dict):
            for key, nested in current.items():
                if _is_sensitive_key(str(key)):
                    collected.update(item for item in _string_values(nested) if len(item) >= 3)
                else:
                    collect(nested)
        elif isinstance(current, list | tuple):
            for nested in current:
                collect(nested)

    collect(value)
    return tuple(sorted(collected, key=len, reverse=True))


def _string_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _string_values(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            yield from _string_values(nested)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def _redact(value: object, sensitive_values: tuple[str, ...]) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, nested in value.items():
            normalized_key = str(key)
            if _is_sensitive_key(normalized_key) and nested is not None:
                redacted[normalized_key] = REDACTED
            else:
                redacted[normalized_key] = _redact(nested, sensitive_values)
        return redacted
    if isinstance(value, list):
        return [_redact(item, sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, sensitive_values) for item in value]
    if isinstance(value, str):
        for sensitive in sensitive_values:
            value = value.replace(sensitive, REDACTED)
    return value
