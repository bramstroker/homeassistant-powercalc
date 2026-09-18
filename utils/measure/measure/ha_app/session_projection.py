from dataclasses import replace
from typing import cast

from measure.ha_app.session import CalibrationSample, SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.runner.interaction import OperatingPoint


def apply_session_event(snapshot: SessionSnapshot, event: SessionEvent) -> SessionSnapshot:
    """Return the session snapshot updated with one runner event."""
    snapshot = replace(snapshot, event_sequence=event.sequence, updated_at=event.created_at)
    data = event.data

    if event.type == SessionEventType.PROGRESS:
        return replace(
            snapshot,
            completed=int(data["completed"]),
            total=int(data["total"]),
            skipped=int(data.get("skipped", 0)),
            phase=str(data["mode"]),
            mode=str(data["mode"]),
            estimated_remaining=str(data["estimated_remaining"]),
        )
    if event.type == SessionEventType.PHASE:
        return replace(snapshot, phase=str(data["message"]))
    if event.type == SessionEventType.OPERATING_POINT:
        return replace(snapshot, operating_point=cast(OperatingPoint, data))
    if event.type == SessionEventType.WARNING:
        warnings = tuple(dict.fromkeys((*snapshot.warnings, str(data["message"]))))[-20:]
        return replace(snapshot, warnings=warnings)
    if event.type == SessionEventType.CHECKPOINT:
        return replace(
            snapshot,
            state=SessionState.AWAITING_CONFIRMATION,
            phase="Waiting for confirmation",
            confirmation_message=str(data["message"]),
            confirmation_action=str(data["action"]) if data.get("action") else None,
        )
    if event.type == SessionEventType.CALIBRATION_SAMPLE:
        return replace(snapshot, calibration_sample=cast(CalibrationSample, data))
    if event.type == SessionEventType.ENTITY_STATES:
        return replace(snapshot, entity_states={str(key): str(value) for key, value in data.get("states", {}).items()})
    return snapshot
