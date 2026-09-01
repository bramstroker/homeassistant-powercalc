from threading import Event, Thread

from measure.execution import FanOperatingPoint, MeasurementCancelledError
from measure.ha_app.session import SessionControl, SessionEvent, SessionEventType
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

    control.phase("Preparing measurement devices")
    control.progress(completed=1, total=10, mode="brightness", estimated_remaining="9s")

    assert [event.sequence for event in events] == [1, 2]
    assert events[0].type == SessionEventType.PHASE
    assert events[0].data == {"message": "Preparing measurement devices"}
    assert events[1].data["completed"] == 1
    assert events[1].data["skipped"] == 0


def test_progress_event_includes_skipped_readings() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)

    control.progress(completed=2, total=12, mode="brightness", estimated_remaining="10s", skipped=1)

    assert events[0].type == SessionEventType.PROGRESS
    assert events[0].data["skipped"] == 1


def test_sample_emits_rounded_power_reading() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)

    control.sample(4.2069)

    assert events[0].type == SessionEventType.SAMPLE
    assert events[0].data == {"power": 4.21}


def test_calibration_sample_emits_rounded_electrical_readings() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)

    control.calibration_sample(60.126, 881.234, 230.257)

    assert events[0].type == SessionEventType.CALIBRATION_SAMPLE
    assert events[0].data == {"power": 60.13, "resistance": 881.23, "voltage": 230.26}


def test_operating_point_emits_typed_device_state() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)
    point = FanOperatingPoint(type="fan", percentage=35, on=True)

    control.operating_point(point)

    assert events[0].type == SessionEventType.OPERATING_POINT
    assert events[0].data == point


def test_entity_states_emits_latest_recorder_states() -> None:
    control = SessionControl()
    events = []
    control.subscribe(events.append)

    control.entity_states({"vacuum.robot": "cleaning", "sensor.robot_battery": "42"})

    assert events[0].type == SessionEventType.ENTITY_STATES
    assert events[0].data == {"states": {"vacuum.robot": "cleaning", "sensor.robot_battery": "42"}}


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
