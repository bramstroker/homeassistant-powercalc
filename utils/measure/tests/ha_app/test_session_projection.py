from dataclasses import replace
from typing import Any

from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.ha_app.session_projection import apply_session_event
import pytest


@pytest.fixture
def snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        id="session",
        state=SessionState.RUNNING,
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:01:00Z",
        phase="Measuring",
        warnings=("Existing warning",),
        event_sequence=3,
    )


@pytest.mark.parametrize(
    "event_type,data,expected_fields",
    [
        (
            SessionEventType.PROGRESS,
            {"completed": 2, "total": 5, "mode": "brightness", "estimated_remaining": "10s", "skipped": 1},
            {
                "completed": 2,
                "total": 5,
                "mode": "brightness",
                "phase": "brightness",
                "estimated_remaining": "10s",
                "skipped": 1,
            },
        ),
        (SessionEventType.PHASE, {"message": "Stabilizing"}, {"phase": "Stabilizing"}),
        (
            SessionEventType.OPERATING_POINT,
            {"type": "light", "on": True, "brightness": 128},
            {"operating_point": {"type": "light", "on": True, "brightness": 128}},
        ),
        (
            SessionEventType.WARNING,
            {"message": "New warning"},
            {"warnings": ("Existing warning", "New warning")},
        ),
        (
            SessionEventType.CHECKPOINT,
            {"message": "Connect charger", "action": "Continue"},
            {
                "state": SessionState.AWAITING_CONFIRMATION,
                "phase": "Waiting for confirmation",
                "confirmation_message": "Connect charger",
                "confirmation_action": "Continue",
            },
        ),
        (
            SessionEventType.CALIBRATION_SAMPLE,
            {"power": 4.2, "resistance": 100.0, "voltage": 230.0},
            {"calibration_sample": {"power": 4.2, "resistance": 100.0, "voltage": 230.0}},
        ),
        (
            SessionEventType.ENTITY_STATES,
            {"states": {"vacuum.robot": "cleaning", "sensor.battery": 42}},
            {"entity_states": {"vacuum.robot": "cleaning", "sensor.battery": "42"}},
        ),
        (SessionEventType.SAMPLE, {"power": 4.2}, {}),
        (SessionEventType.LOG, {"message": "Reading power"}, {}),
        (SessionEventType.STATE, {"state": "running"}, {}),
    ],
)
def test_event_updates_only_its_snapshot_fields(
    snapshot: SessionSnapshot,
    event_type: SessionEventType,
    data: dict[str, Any],
    expected_fields: dict[str, Any],
) -> None:
    original = snapshot.to_dict()
    event = SessionEvent(sequence=4, type=event_type, created_at="2026-09-18T10:02:00Z", data=data)

    updated = apply_session_event(snapshot, event)

    assert updated == replace(snapshot, event_sequence=4, updated_at=event.created_at, **expected_fields)
    assert snapshot.to_dict() == original


@pytest.mark.parametrize("action", [None, ""])
def test_checkpoint_clears_previous_action(snapshot: SessionSnapshot, action: str | None) -> None:
    snapshot = replace(snapshot, confirmation_action="Old action")
    event = SessionEvent(4, SessionEventType.CHECKPOINT, snapshot.updated_at, {"message": "Ready?", "action": action})

    assert apply_session_event(snapshot, event).confirmation_action is None


def test_warning_history_is_deduplicated_and_bounded(snapshot: SessionSnapshot) -> None:
    warnings = tuple(f"Warning {index}" for index in range(20))
    snapshot = replace(snapshot, warnings=(*warnings, warnings[-1]))
    duplicate = SessionEvent(4, SessionEventType.WARNING, snapshot.updated_at, {"message": warnings[-1]})
    new_warning = SessionEvent(5, SessionEventType.WARNING, snapshot.updated_at, {"message": "Newest warning"})

    updated = apply_session_event(snapshot, duplicate)
    assert updated.warnings == warnings
    assert apply_session_event(updated, new_warning).warnings == (*warnings[1:], "Newest warning")


def test_progress_defaults_skipped_count_to_zero(snapshot: SessionSnapshot) -> None:
    snapshot = replace(snapshot, skipped=3)
    event = SessionEvent(
        4,
        SessionEventType.PROGRESS,
        snapshot.updated_at,
        {"completed": 1, "total": 2, "mode": "brightness", "estimated_remaining": "10s"},
    )

    updated = apply_session_event(snapshot, event)

    assert updated.skipped == 0
    assert updated.progress == 50
