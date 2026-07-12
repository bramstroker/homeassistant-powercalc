from __future__ import annotations

from threading import Event, Thread

from measure.session import MeasurementCancelledError, SessionControl, SessionEvent, SessionEventType
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


def test_sample_emits_rounded_power_reading() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)

    control.sample(4.2069)

    assert events[0].type == SessionEventType.SAMPLE
    assert events[0].data == {"power": 4.21}


def test_confirmation_emits_checkpoint_and_continues() -> None:
    control = SessionControl()
    events = []
    checkpoint = Event()

    def record(event: SessionEvent) -> None:
        events.append(event)
        checkpoint.set()

    control.subscribe(record)
    worker = Thread(target=control.confirm, args=("Ready",))
    worker.start()
    assert checkpoint.wait(1)
    control.continue_run()
    worker.join()

    assert events[0].type == SessionEventType.CHECKPOINT
    assert events[0].data["message"] == "Ready"
