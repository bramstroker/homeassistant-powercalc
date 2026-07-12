from __future__ import annotations

from pathlib import Path
from threading import Event
import time

from measure.coordinator import MeasurementCoordinator, SessionConflictError
from measure.request import LightMeasurementRequest, LightMeasurementRequestModel, ResumePolicy
from measure.runner.runner import RunnerResult
from measure.session import SessionControl, SessionSnapshot, SessionState
from measure.storage import SessionStorage
import pytest


def request_model() -> LightMeasurementRequestModel:
    return LightMeasurementRequestModel(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        light_entity_id="light.test",
        power_entity_id="sensor.test_power",
    )


def wait_for_state(coordinator: MeasurementCoordinator, state: SessionState) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if coordinator.current and coordinator.current.state == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"Session did not reach {state}")


class CompletingService:
    def run(
        self,
        request: LightMeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        directory = output_root / request.model_id
        directory.mkdir(parents=True)
        (directory / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")
        control.progress(completed=1, total=1, mode="brightness", estimated_remaining="0s")
        return RunnerResult(model_json_data={}), directory


class BlockingService:
    def __init__(self, started: Event) -> None:
        self.started = started

    def run(
        self,
        request: LightMeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        self.started.set()
        control.wait(60)
        raise AssertionError("Cancelled wait returned")


def test_coordinator_completes_and_persists_files(tmp_path: Path) -> None:
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)

    coordinator.start(request_model())
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
    coordinator.start(request_model())
    assert started.wait(1)

    with pytest.raises(SessionConflictError):
        coordinator.start(request_model())

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
    storage.create(current, request_model())
    coordinator = MeasurementCoordinator(storage, CompletingService)

    with pytest.raises(SessionConflictError, match="no compatible complete row"):
        coordinator.resume()


def test_overwrite_removes_previous_session_files(tmp_path: Path) -> None:
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)
    first = coordinator.start(request_model())
    wait_for_state(coordinator, SessionState.COMPLETED)
    old_directory = coordinator.storage.session_directory(first.id)

    coordinator.start(request_model().model_copy(update={"resume_policy": ResumePolicy.OVERWRITE}))

    assert not old_directory.exists()
