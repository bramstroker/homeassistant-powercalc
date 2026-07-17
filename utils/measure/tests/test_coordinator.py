from __future__ import annotations

from pathlib import Path
from threading import Event
import time

from measure.controller.light.spec import DummyLightControllerSpec
from measure.execution import LightOperatingPoint
from measure.ha_app.coordinator import MeasurementCoordinator, SessionConflictError, SessionMeasurementService
from measure.ha_app.session import SessionControl, SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import (
    LightMeasurementRequest,
    MeasurementRequest,
    ResumePolicy,
)
from measure.runner.runner import RunnerResult
import pytest


def light_request() -> LightMeasurementRequest:
    return LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
    )


def wait_for_state(coordinator: MeasurementCoordinator, state: SessionState) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if coordinator.current and coordinator.current.state == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"Session did not reach {state}")


class CompletingService(SessionMeasurementService):
    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        directory = output_root / request.model_id
        directory.mkdir(parents=True)
        (directory / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")
        control.progress(completed=1, total=1, mode="brightness", estimated_remaining="0s")
        return RunnerResult(model_json_data={})


class BlockingService(SessionMeasurementService):
    def __init__(self, started: Event) -> None:
        self.started = started

    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        self.started.set()
        control.wait(60)
        raise AssertionError("Cancelled wait returned")


class SamplingService(SessionMeasurementService):
    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        control.sample(4.2)
        return RunnerResult(model_json_data={})


class OperatingPointService(SessionMeasurementService):
    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        control.operating_point(LightOperatingPoint(type="light", on=True, brightness=128))
        control.wait(60)
        raise AssertionError("Cancelled wait returned")


class CheckpointService(SessionMeasurementService):
    def __init__(self, continued: Event) -> None:
        self.continued = continued

    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        control.phase("Preparing operator checkpoint")
        control.confirm("Place the device on its charger, then start the measurement.")
        self.continued.set()
        return RunnerResult(model_json_data={})


def test_coordinator_completes_and_persists_files(tmp_path: Path) -> None:
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)

    coordinator.start(light_request())
    wait_for_state(coordinator, SessionState.COMPLETED)

    assert coordinator.current is not None
    assert coordinator.current.progress == 100
    assert coordinator.current.files == ("LCT010/brightness.csv",)
    assert [(event.sequence, event.data["state"]) for event in coordinator.events_since(1)] == [
        (2, SessionState.COMPLETED),
    ]


def test_coordinator_rejects_concurrent_start_and_cancels(tmp_path: Path) -> None:
    started = Event()
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), lambda: BlockingService(started))
    coordinator.start(light_request())
    assert started.wait(1)

    duplicate = light_request()
    with pytest.raises(SessionConflictError):
        coordinator.start(duplicate)

    coordinator.cancel()
    wait_for_state(coordinator, SessionState.CANCELLED)
    assert coordinator.cancel().state == SessionState.CANCELLED


def test_coordinator_rejects_resume_without_compatible_output(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    current = SessionSnapshot(
        id="failed",
        state=SessionState.FAILED,
        created_at="2026-07-12T12:00:00Z",
        updated_at="2026-07-12T12:00:00Z",
    )
    storage.create(current, light_request())
    coordinator = MeasurementCoordinator(storage, CompletingService)

    with pytest.raises(SessionConflictError, match="no compatible complete row"):
        coordinator.resume()


def test_overwrite_removes_previous_session_files(tmp_path: Path) -> None:
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)
    first = coordinator.start(light_request())
    wait_for_state(coordinator, SessionState.COMPLETED)
    old_directory = coordinator.storage.session_directory(first.id)

    coordinator.start(light_request().model_copy(update={"resume_policy": ResumePolicy.OVERWRITE}))

    assert not old_directory.exists()


def test_transient_sample_does_not_reuse_terminal_event_sequence(tmp_path: Path) -> None:
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), SamplingService)

    coordinator.start(light_request())
    wait_for_state(coordinator, SessionState.COMPLETED)

    events = coordinator.events_since(0)
    assert [event.sequence for event in events] == [1, 2]
    assert len({event.sequence for event in events}) == len(events)


def test_coordinator_reloads_persisted_events_for_reconnect(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    coordinator = MeasurementCoordinator(storage, CompletingService)
    coordinator.start(light_request())
    wait_for_state(coordinator, SessionState.COMPLETED)

    reloaded = MeasurementCoordinator(storage, CompletingService)

    assert [event.sequence for event in reloaded.events_since(0)] == [1, 2]


def test_coordinator_projects_and_persists_operating_point(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    coordinator = MeasurementCoordinator(storage, OperatingPointService)
    coordinator.start(light_request())

    deadline = time.monotonic() + 1
    while coordinator.current and coordinator.current.operating_point is None and time.monotonic() < deadline:
        time.sleep(0.01)

    assert coordinator.current is not None
    assert coordinator.current.operating_point == {"type": "light", "on": True, "brightness": 128}
    persisted = storage.load_current()
    assert persisted is not None
    assert persisted.operating_point == coordinator.current.operating_point

    coordinator.cancel()
    wait_for_state(coordinator, SessionState.CANCELLED)


def test_coordinator_projects_phase_and_confirmation_message(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    continued = Event()
    coordinator = MeasurementCoordinator(storage, lambda: CheckpointService(continued))

    coordinator.start(light_request())
    wait_for_state(coordinator, SessionState.AWAITING_CONFIRMATION)

    assert coordinator.current is not None
    assert coordinator.current.phase == "Waiting for confirmation"
    assert coordinator.current.confirmation_message == "Place the device on its charger, then start the measurement."
    persisted = storage.load_current()
    assert persisted is not None
    assert persisted.confirmation_message == coordinator.current.confirmation_message

    confirmed = coordinator.confirm()
    assert confirmed.state == SessionState.RUNNING
    assert confirmed.phase == "Starting measurement"
    assert confirmed.confirmation_message is None
    assert continued.wait(1)
    wait_for_state(coordinator, SessionState.COMPLETED)
