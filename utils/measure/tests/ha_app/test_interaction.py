from measure.cancellation import MeasurementCancelledError
from measure.ha_app.interaction import SessionInteraction
from measure.ha_app.session import SessionControl, SessionEvent, SessionEventType
import pytest


@pytest.mark.parametrize("default", [True, False])
def test_runtime_choice_uses_and_reports_default(default: bool) -> None:
    control = SessionControl()
    events: list[SessionEvent] = []
    control.subscribe(events.append)

    assert SessionInteraction(control).choose("Repeat measurement?", default=default) is default
    assert events[0].type == SessionEventType.LOG
    choice = "yes" if default else "no"
    assert events[0].data == {"message": f"Repeat measurement? Using the non-interactive default: {choice}."}


@pytest.mark.parametrize("remaining_seconds, expected", [(None, ""), (12.9, "12s")])
def test_progress_formats_remaining_time(remaining_seconds: float | None, expected: str) -> None:
    control = SessionControl()
    events: list[SessionEvent] = []
    control.subscribe(events.append)

    SessionInteraction(control).progress(3, 10, phase="brightness", remaining_seconds=remaining_seconds, skipped=1)

    assert events[0].type == SessionEventType.PROGRESS
    assert events[0].data == {
        "completed": 3,
        "total": 10,
        "mode": "brightness",
        "estimated_remaining": expected,
        "skipped": 1,
    }


def test_session_interaction_reports_preparation_and_live_state() -> None:
    control = SessionControl()
    events: list[SessionEvent] = []

    def handle_event(event: SessionEvent) -> None:
        events.append(event)
        if event.type == SessionEventType.CHECKPOINT:
            control.continue_run()

    control.subscribe(handle_event)
    interaction = SessionInteraction(control)
    interaction.confirm("Turn device on", action="turn_on")
    interaction.notify("Ready")
    interaction.phase("Measuring")
    interaction.operating_point({"type": "fan", "percentage": 50, "on": True})
    interaction.entity_states({"vacuum.test": "cleaning"})
    interaction.wait(0)
    interaction.checkpoint()

    assert [event.type for event in events] == [
        SessionEventType.CHECKPOINT,
        SessionEventType.LOG,
        SessionEventType.PHASE,
        SessionEventType.OPERATING_POINT,
        SessionEventType.ENTITY_STATES,
    ]
    assert [event.data for event in events] == [
        {"message": "Turn device on", "action": "turn_on"},
        {"message": "Ready"},
        {"message": "Measuring"},
        {"type": "fan", "percentage": 50, "on": True},
        {"states": {"vacuum.test": "cleaning"}},
    ]


def test_session_interaction_wait_honors_cancellation() -> None:
    control = SessionControl()
    interaction = SessionInteraction(control)
    control.cancel()

    with pytest.raises(MeasurementCancelledError):
        interaction.wait(60)


def test_session_interaction_checkpoint_honors_cancellation() -> None:
    control = SessionControl()
    interaction = SessionInteraction(control)
    control.cancel()

    with pytest.raises(MeasurementCancelledError):
        interaction.checkpoint()
