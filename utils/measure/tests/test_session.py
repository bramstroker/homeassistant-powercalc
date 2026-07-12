from __future__ import annotations

from measure.session import MeasurementCancelledError, SessionControl, SessionEventType
import pytest


def test_cancel_is_idempotent_and_checkpoint_raises() -> None:
    control = SessionControl()

    control.cancel()
    control.cancel()

    with pytest.raises(MeasurementCancelledError):
        control.checkpoint()


def test_events_are_sequenced_and_delivered() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)

    control.emit(SessionEventType.STATE, {"state": "running"})
    control.progress(completed=1, total=10, mode="brightness", estimated_remaining="9s")

    assert [event.sequence for event in events] == [1, 2]
    assert events[1].data["completed"] == 1
