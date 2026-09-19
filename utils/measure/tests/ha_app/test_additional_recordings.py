from dataclasses import replace
import json
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from measure.analyser.execution import RecorderAnalysisExecution
from measure.analyser.recording import load_recordings
from measure.cancellation import MeasurementCancelledError
from measure.ha_app.api import create_app
from measure.ha_app.coordinator import MeasurementCoordinator, SessionConflictError, SessionExecutionContext
from measure.ha_app.session import SessionControl, SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.recording.context import build_recording_context
from measure.recording.files import find_recording_paths, select_recording_filenames
from measure.request import AverageMeasurementRequest, RecorderMeasurementRequest
from measure.runner.runner import RunnerResult
import pytest


@pytest.fixture
def recorder_request() -> RecorderMeasurementRequest:
    return RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.device",),
    )


def test_recording_names_are_ordered_and_exclude_unrelated_files() -> None:
    assert select_recording_filenames(
        [
            "record.jsonl",
            "record-10.jsonl",
            "record-2.jsonl",
            "record-1.jsonl",
            "record-other.jsonl",
            "record-0.jsonl",
            "record-01.jsonl",
            "record-².jsonl",
            "analyser.json",
        ]
    ) == ["record-1.jsonl", "record-2.jsonl", "record-10.jsonl", "record.jsonl"]


def write_recording(path: Path, request: RecorderMeasurementRequest, state: str) -> None:
    records = [build_recording_context(request).build_metadata_record()]
    records.extend(
        {
            "record_type": "sample",
            "elapsed_seconds": index * 2,
            "power": 5.2 if state == "on" else 0.2,
            "entities": {"switch.device": {"state": state, "attributes": {}}},
        }
        for index in range(10)
    )
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def retained_session(storage: SessionStorage, request: RecorderMeasurementRequest) -> SessionSnapshot:
    snapshot = SessionSnapshot(
        id="recording",
        state=SessionState.COMPLETED,
        created_at="2026-09-17T08:00:00Z",
        updated_at="2026-09-17T08:00:00Z",
        completed=10,
        event_sequence=5,
        entity_states={"switch.device": "off"},
        summary={"Samples recorded": "10"},
    )
    storage.create(snapshot, request)
    output = storage.artifact_directory(snapshot.id, request.model_id)
    output.mkdir()
    write_recording(output / request.export_filename, request, "off")
    return snapshot


def test_record_more_keeps_session_and_fits_both_runs(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest
) -> None:
    storage = SessionStorage(tmp_path)
    previous = retained_session(storage, recorder_request)
    output = storage.artifact_directory(previous.id, recorder_request.model_id)
    original = (output / "record.jsonl").read_bytes()
    service = MagicMock()
    release = Event()

    def record(
        request: RecorderMeasurementRequest, control: SessionControl, context: SessionExecutionContext
    ) -> RunnerResult:
        assert release.wait(2)
        assert request == recorder_request
        assert context.session_id == previous.id
        write_recording(context.artifact_directory / request.export_filename, request, "on")
        return RunnerResult(
            model_json_data={}, summary=RecorderAnalysisExecution().run(request, context.artifact_directory)
        )

    service.run.side_effect = record
    coordinator = MeasurementCoordinator(storage, lambda: service)
    finished = Event()
    coordinator.subscribe(lambda: finished.set() if coordinator.current.state == SessionState.COMPLETED else None)

    started = coordinator.record_more(previous.id)
    assert started.id == previous.id
    assert started.created_at == previous.created_at
    assert started.completed == 0
    assert started.entity_states == {}
    assert started.summary == previous.summary
    assert (output / "record-1.jsonl").read_bytes() == original
    assert not (output / "record.jsonl").exists()
    release.set()
    assert finished.wait(2)

    completed = coordinator.get(previous.id)
    assert completed.event_sequence > previous.event_sequence
    assert len(storage.list_sessions()) == 1
    assert storage.load_request(previous.id) == recorder_request
    assert completed.summary["Recordings analysed"] == "2"
    assert completed.summary["Samples analysed"] == "20"
    assert completed.summary["Recording analysis"] == "Fixed power profile created"
    assert json.loads((output / "model.json").read_text())["fixed_config"] == {"power": 5.2}
    loaded = load_recordings(find_recording_paths(output, recorder_request.export_filename))
    assert {sample.recording_id for sample in loaded.dataset.samples} == {0, 1}
    assert loaded.dataset.samples[0].elapsed_seconds == loaded.dataset.samples[10].elapsed_seconds == 0

    # Reanalysis after reopening the app includes both runs, not just the latest file.
    reopened = MeasurementCoordinator(SessionStorage(tmp_path), lambda: service)
    assert reopened.analyse(previous.id).summary["Samples analysed"] == "20"
    assert (output / "record-1.jsonl").read_bytes() == original
    assert (output / recorder_request.export_filename).is_file()


def test_failed_record_more_keeps_the_previous_analysis_summary(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest
) -> None:
    """A meter failure during an extra run must not erase the analysis already produced."""

    storage = SessionStorage(tmp_path)
    previous = retained_session(storage, recorder_request)
    service = MagicMock()
    service.run.side_effect = RuntimeError("power meter disappeared")
    coordinator = MeasurementCoordinator(storage, lambda: service)
    finished = Event()
    coordinator.subscribe(lambda: finished.set() if coordinator.current.state == SessionState.FAILED else None)

    coordinator.record_more(previous.id)

    assert finished.wait(2)
    failed = coordinator.get(previous.id)
    assert failed.state == SessionState.FAILED
    assert failed.summary == previous.summary
    assert storage.can_analyse(previous.id)


def test_archiving_is_collision_safe_and_recoverable(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest
) -> None:
    storage = SessionStorage(tmp_path)
    session = retained_session(storage, recorder_request)
    output = storage.artifact_directory(session.id, recorder_request.model_id)
    original = (output / "record.jsonl").read_bytes()
    (output / "record-1.jsonl").write_bytes(original)
    (output / "record-2.jsonl").symlink_to(output / "absent.jsonl")
    (output / "record-10.jsonl").write_bytes(original)
    (output / "record-other.jsonl").write_text("not a recording")
    (output / "record-4.jsonl").mkdir()

    storage.archive_recording(session.id, recorder_request)
    storage.archive_recording(session.id, recorder_request)

    assert [path.name for path in find_recording_paths(output, "record.jsonl")] == [
        "record-1.jsonl",
        "record-3.jsonl",
        "record-10.jsonl",
    ]
    assert (output / "record-1.jsonl").read_bytes() == original
    assert (output / "record-3.jsonl").read_bytes() == original
    assert storage.can_analyse(session.id)
    storage.write_snapshot(replace(session, state=SessionState.RUNNING))
    recovered = SessionStorage(tmp_path).load_current()
    assert recovered.state == SessionState.FAILED
    assert storage.can_analyse(recovered.id)

    (output / "record.jsonl").symlink_to(output / "record-1.jsonl")
    with pytest.raises(ValueError, match="symbolic link"):
        storage.archive_recording(session.id, recorder_request)


@pytest.mark.parametrize("error", [MeasurementCancelledError("Stopped"), RuntimeError("Connection lost")])
def test_interrupted_additional_run_preserves_recordings_and_can_retry(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest, error: Exception
) -> None:
    storage = SessionStorage(tmp_path)
    session = retained_session(storage, recorder_request)
    output = storage.artifact_directory(session.id, recorder_request.model_id)
    original = (output / "record.jsonl").read_bytes()
    service = MagicMock()
    service.run.side_effect = error
    coordinator = MeasurementCoordinator(storage, lambda: service)
    finished = Event()
    terminal_states = {SessionState.COMPLETED, SessionState.CANCELLED, SessionState.FAILED}
    coordinator.subscribe(lambda: finished.set() if coordinator.current.state in terminal_states else None)

    coordinator.record_more(session.id)
    assert finished.wait(2)
    assert (output / "record-1.jsonl").read_bytes() == original
    assert not (output / "record.jsonl").exists()
    assert storage.can_analyse(session.id)

    def record(
        request: RecorderMeasurementRequest, control: SessionControl, context: SessionExecutionContext
    ) -> RunnerResult:
        write_recording(context.artifact_directory / request.export_filename, request, "on")
        return RunnerResult(
            model_json_data={}, summary=RecorderAnalysisExecution().run(request, context.artifact_directory)
        )

    service.run.side_effect = record
    finished.clear()
    coordinator.record_more(session.id)
    assert finished.wait(2)
    assert coordinator.current.state == SessionState.COMPLETED
    assert coordinator.current.summary["Samples analysed"] == "20"
    assert (output / "record-1.jsonl").read_bytes() == original
    assert not (output / "record-2.jsonl").exists()


@pytest.mark.parametrize("state", [SessionState.COMPLETED, SessionState.CANCELLED, SessionState.FAILED])
def test_record_more_reopens_historical_sessions(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest, state: SessionState
) -> None:
    storage = SessionStorage(tmp_path)
    session = retained_session(storage, recorder_request)
    storage.write_snapshot(replace(session, state=state))
    storage.create(replace(session, id="other"), AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()))
    service = MagicMock()
    service.run.return_value = RunnerResult(model_json_data={})
    coordinator = MeasurementCoordinator(storage, lambda: service)
    finished = Event()
    coordinator.subscribe(lambda: finished.set() if coordinator.current.state == SessionState.COMPLETED else None)
    coordinator.record_more(session.id)
    assert finished.wait(2)
    assert coordinator.current.id == session.id
    assert storage.load_current().id == session.id


def test_record_more_rejects_ineligible_sessions(tmp_path: Path, recorder_request: RecorderMeasurementRequest) -> None:
    storage = SessionStorage(tmp_path)
    session = retained_session(storage, recorder_request)
    coordinator = MeasurementCoordinator(storage, MagicMock())
    with pytest.raises(SessionConflictError, match="does not exist"):
        coordinator.record_more("missing")
    storage.create(replace(session, id="average"), AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()))
    with pytest.raises(SessionConflictError, match="no profile recording"):
        coordinator.record_more("average")
    storage.create(replace(session, id="active", state=SessionState.RUNNING), recorder_request)
    with pytest.raises(SessionConflictError, match="no profile recording"):
        coordinator.record_more("active")


def test_combined_analysis_keeps_existing_voltage_range(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest
) -> None:
    write_recording(tmp_path / "record-1.jsonl", recorder_request, "off")
    write_recording(tmp_path / "record.jsonl", recorder_request, "on")
    (tmp_path / "model.json").write_text(json.dumps({"voltage_range": {"min": 220, "max": 240}}))

    RecorderAnalysisExecution().run(recorder_request, tmp_path, voltages=[229, 231])

    assert json.loads((tmp_path / "model.json").read_text())["voltage_range"] == {"min": 220, "max": 240}


def test_combined_recordings_allow_availability_changes_but_reject_changed_entities(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest
) -> None:
    first = tmp_path / "record-1.jsonl"
    latest = tmp_path / "record.jsonl"
    write_recording(first, recorder_request, "off")
    write_recording(latest, recorder_request, "on")
    lines = latest.read_text().splitlines()
    metadata = json.loads(lines[0])
    metadata["entities"][0].update(has_live_state=False, disabled_by="user")
    latest.write_text("\n".join([json.dumps(metadata), *lines[1:]]) + "\n")
    assert len(load_recordings([first, latest]).dataset.samples) == 20

    metadata["entities"][0]["entity_id"] = "switch.other"
    latest.write_text("\n".join([json.dumps(metadata), *lines[1:]]) + "\n")
    with pytest.raises(ValueError, match="same recipe and entities"):
        load_recordings([first, latest])


@pytest.mark.parametrize("outcome", ["success", "preflight_failure", "conflict"])
def test_record_more_endpoint_runs_preflight_before_archiving(
    tmp_path: Path, recorder_request: RecorderMeasurementRequest, outcome: str
) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106
    context = app.state.context
    session = retained_session(context.storage, recorder_request)
    service = MagicMock()
    service.run.return_value = RunnerResult(model_json_data={})
    context.coordinator = MeasurementCoordinator(context.storage, lambda: service)
    test_client = TestClient(app, client=("127.0.0.1", 50000))
    output = context.storage.artifact_directory(session.id, recorder_request.model_id)
    original = (output / "record.jsonl").read_bytes()
    finished = Event()
    context.coordinator.subscribe(
        lambda: finished.set() if context.coordinator.current.state == SessionState.COMPLETED else None
    )

    with patch("measure.ha_app.routes.sessions.run_preflight") as preflight:
        if outcome == "preflight_failure":
            preflight.side_effect = HTTPException(status_code=422, detail="Vacuum unavailable")
        if outcome == "conflict":
            with patch.object(context.coordinator, "record_more", side_effect=SessionConflictError("Already active")):
                response = test_client.post(f"/api/sessions/{session.id}/record-more")
        else:
            response = test_client.post(f"/api/sessions/{session.id}/record-more")
        preflight.assert_called_once_with(context, recorder_request)

    if outcome == "success":
        assert response.status_code == 200
        assert response.json()["session_id"] == session.id
        assert (output / "record-1.jsonl").read_bytes() == original
        assert finished.wait(2)
    else:
        assert response.status_code == (422 if outcome == "preflight_failure" else 409)
        assert (output / "record.jsonl").read_bytes() == original
        assert not (output / "record-1.jsonl").exists()


def test_record_more_endpoint_rejects_missing_and_non_recorder_sessions(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106
    context = app.state.context
    snapshot = SessionSnapshot(id="average", state=SessionState.COMPLETED, created_at="now", updated_at="now")
    context.storage.create(snapshot, AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()))
    test_client = TestClient(app, client=("127.0.0.1", 50000))
    assert test_client.post("/api/sessions/missing/record-more").status_code == 404
    assert test_client.post("/api/sessions/average/record-more").status_code == 409
