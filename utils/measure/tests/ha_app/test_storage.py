from dataclasses import replace
import json
import logging
from pathlib import Path

from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.spec import DummyLightControllerSpec
from measure.dummy_load import DummyLoadCalibration
from measure.ha_app.contribution.coordinator import ContributionApiCoordinator
from measure.ha_app.contribution.models import ContributionPreviewResponse, ContributionState, ContributionStatus
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState, utc_now
from measure.ha_app.shelly_credentials import ShellyCredentials
from measure.ha_app.storage import SessionStorage
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import (
    LightMeasurementRequest,
    RecorderMeasurementRequest,
    RecorderProfileRecipe,
    RecorderPurpose,
)
import pytest


def light_request() -> LightMeasurementRequest:
    return LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
    )


def snapshot(state: SessionState = SessionState.READY) -> SessionSnapshot:
    now = utc_now()
    return SessionSnapshot(id="a1b2-c3d4", state=state, created_at=now, updated_at=now)


@pytest.mark.parametrize("session_id", ["", "../outside", "nested/session", "session.json"])
def test_storage_rejects_unsafe_session_ids(tmp_path: Path, session_id: str) -> None:
    storage = SessionStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid session id"):
        storage.session_directory(session_id)

    assert list(storage.sessions_root.iterdir()) == []


@pytest.mark.parametrize("contents", ["not json", "[]", "{}"])
def test_clear_current_removes_corrupt_pointer(tmp_path: Path, contents: str) -> None:
    storage = SessionStorage(tmp_path)
    pointer = tmp_path / "current.json"
    pointer.write_text(contents, encoding="utf-8")

    storage.clear_current("a1b2-c3d4")

    assert not pointer.exists()


def test_clear_current_preserves_pointer_to_another_session(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot(SessionState.COMPLETED)
    storage.create(current, light_request())

    storage.clear_current("other-session")

    assert storage.load_current() == current


def test_snapshot_id_must_match_session_directory(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    directory = storage.create(snapshot(), light_request())
    state_path = directory / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["id"] = "other-session"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="Session state id does not match its directory"):
        storage.load_snapshot("a1b2-c3d4")


def test_session_listing_ignores_files_and_symbolic_links(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot()
    directory = storage.create(current, light_request())
    (storage.sessions_root / "notes.txt").write_text("notes", encoding="utf-8")
    (storage.sessions_root / "linked-session").symlink_to(directory, target_is_directory=True)

    assert storage.list_sessions() == [current]


def test_missing_session_has_no_outputs_or_resume_data(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)

    assert storage.list_files("missing-session") == []
    assert not storage.can_resume("missing-session")
    with pytest.raises(FileNotFoundError):
        storage.session_size("missing-session")


def test_light_session_cannot_be_analysed_as_a_recording(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())

    assert not storage.can_analyse("a1b2-c3d4")


def test_measurement_only_recording_cannot_resume_or_be_analysed(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    request = RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec())
    storage.create(snapshot(), request)
    output = storage.artifact_directory("a1b2-c3d4", request.model_id)
    output.mkdir()
    (output / request.export_filename).write_text("recording", encoding="utf-8")

    assert not storage.can_resume("a1b2-c3d4")
    assert not storage.can_analyse("a1b2-c3d4")


def test_storage_round_trips_current_session(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())

    loaded = storage.load_current()

    assert loaded is not None
    assert loaded.id == "a1b2-c3d4"
    assert storage.load_request(loaded.id).model_id == "LCT010"
    directory = storage.session_directory(loaded.id)
    persisted_request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    persisted_state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert persisted_request["measure_type"] == "light"
    assert persisted_state["state"] == loaded.state


def test_unknown_model_uses_a_session_scoped_artifact_directory(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    first = storage.artifact_directory("first", "")
    second = storage.artifact_directory("second", "")
    assert first == storage.output_directory("first") / "measurement"
    assert first != second
    assert storage.artifact_directory("first", "LCT010") == storage.output_directory("first") / "LCT010"


def test_storage_lists_retained_sessions_and_clears_deleted_current_pointer(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    first = SessionSnapshot(
        id="first-session",
        state=SessionState.COMPLETED,
        created_at="2026-07-12T12:00:00Z",
        updated_at="2026-07-12T12:05:00Z",
    )
    second = SessionSnapshot(
        id="second-session",
        state=SessionState.CANCELLED,
        created_at="2026-07-13T12:00:00Z",
        updated_at="2026-07-13T12:05:00Z",
    )
    storage.create(first, light_request())
    storage.create(second, light_request())
    (storage.sessions_root / "incomplete-session").mkdir()

    retained = storage.list_sessions()

    assert [item.id for item in retained] == [second.id, first.id]
    assert storage.session_size(first.id) > 0

    storage.delete_session(second.id)

    assert storage.load_current() is None
    assert storage.load_snapshot(first.id) == first


def test_storage_round_trips_bounded_event_replay(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot()
    storage.create(current, light_request())
    for sequence in range(1, 4):
        storage.append_event(
            current.id,
            SessionEvent(
                sequence=sequence,
                type=SessionEventType.LOG,
                created_at="2026-07-12T12:00:00Z",
                data={"message": str(sequence)},
            ),
            durable=False,
        )

    events = storage.load_events(current.id, limit=2)
    all_events = storage.load_events(current.id, limit=None)

    assert [event.sequence for event in events] == [2, 3]
    assert [event.sequence for event in all_events] == [1, 2, 3]


def test_clearing_current_session_retains_history_and_allows_reselection(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot(SessionState.COMPLETED)
    measurement_request = light_request()
    storage.create(current, measurement_request)

    storage.clear_current()
    storage.clear_current()

    assert storage.load_current() is None
    assert storage.load_snapshot(current.id) == current
    assert storage.load_request(current.id) == measurement_request
    assert [item.id for item in storage.list_sessions()] == [current.id]

    storage.set_current(current.id)

    assert storage.load_current() == current


def test_repeated_session_deletion_preserves_another_current_session(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    previous = snapshot(SessionState.COMPLETED)
    storage.create(previous, light_request())
    current = replace(previous, id="current-session")
    storage.create(current, light_request())

    storage.delete_session(previous.id)
    storage.delete_session(previous.id)

    assert not storage.session_directory(previous.id).exists()
    assert storage.load_current() == current
    assert [item.id for item in storage.list_sessions()] == [current.id]


def test_storage_recovers_from_truncated_final_event(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot()
    storage.create(current, light_request())
    storage.append_event(
        current.id,
        SessionEvent(
            sequence=1,
            type=SessionEventType.LOG,
            created_at="2026-07-12T12:00:00Z",
            data={"message": "complete"},
        ),
    )
    event_path = storage.session_directory(current.id) / "events.jsonl"
    with event_path.open("a", encoding="utf-8") as file:
        file.write('{"sequence":2')

    with caplog.at_level(logging.WARNING, logger="measure"):
        events = storage.load_events(current.id)

    assert [event.sequence for event in events] == [1]
    assert "truncated final session event" in caplog.text


@pytest.mark.parametrize("contents", ["not json", "[]", "{}", '{"id":"missing-session"}'])
def test_invalid_current_pointer_is_removed_without_deleting_retained_session(tmp_path: Path, contents: str) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot(SessionState.COMPLETED)
    storage.create(current, light_request())
    pointer = tmp_path / "current.json"
    pointer.write_text(contents, encoding="utf-8")

    assert storage.load_current() is None
    assert not pointer.exists()
    assert storage.load_snapshot(current.id) == current


def test_event_replay_ignores_blank_lines(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())
    event = SessionEvent(sequence=1, type=SessionEventType.LOG, created_at=utc_now(), data={"message": "saved"})
    storage.append_event("a1b2-c3d4", event)
    path = storage.session_directory("a1b2-c3d4") / "events.jsonl"
    path.write_text("\n  \n" + path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert storage.load_events("a1b2-c3d4") == [event]


@pytest.mark.parametrize("contents", ["", "\n  \n"], ids=["empty", "blank-lines"])
def test_event_replay_accepts_logs_without_events(
    tmp_path: Path,
    contents: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot()
    storage.create(current, light_request())
    path = storage.session_directory(current.id) / "events.jsonl"
    path.write_text(contents, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="measure"):
        events = storage.load_events(current.id)

    assert events == []
    assert caplog.records == []
    assert path.read_text(encoding="utf-8") == contents
    assert storage.load_snapshot(current.id) == current


@pytest.mark.parametrize("invalid_event", ["[]", '{"data":[]}', '{"sequence":'])
@pytest.mark.parametrize("is_final", [False, True])
def test_event_recovery_only_tolerates_truncated_final_json(
    tmp_path: Path,
    invalid_event: str,
    is_final: bool,
) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())
    event = SessionEvent(sequence=1, type=SessionEventType.LOG, created_at=utc_now(), data={"message": "saved"})
    storage.append_event("a1b2-c3d4", event)
    path = storage.session_directory("a1b2-c3d4") / "events.jsonl"
    valid_event = path.read_text(encoding="utf-8")
    contents = valid_event + invalid_event if is_final else invalid_event + "\n" + valid_event
    path.write_text(contents, encoding="utf-8")

    if is_final and invalid_event == '{"sequence":':
        assert storage.load_events("a1b2-c3d4") == [event]
    else:
        message = "Expecting value" if invalid_event == '{"sequence":' else "Persisted session event must be an object"
        with pytest.raises(ValueError, match=message):
            storage.load_events("a1b2-c3d4")
    assert path.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize("provider", ["shelly", "tapo"])
@pytest.mark.parametrize("contents", ["not json", "[]", "{}"])
def test_invalid_credentials_are_treated_as_unconfigured(tmp_path: Path, provider: str, contents: str) -> None:
    storage = SessionStorage(tmp_path)
    path = tmp_path / f"{provider}_credentials.json"
    path.write_text(contents, encoding="utf-8")

    credentials = storage.load_shelly_credentials() if provider == "shelly" else storage.load_tapo_credentials()

    assert credentials is None
    assert path.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize(
    "brightness,mired,resumable",
    [(1, MIN_MIRED, True), (1, MAX_MIRED, True), (1, MIN_MIRED - 1, False), (1, MAX_MIRED + 1, False), (2, 250, False)],
)
def test_color_temperature_resume_requires_compatible_brightness_and_mired_range(
    tmp_path: Path,
    brightness: int,
    mired: int,
    resumable: bool,
) -> None:
    storage = SessionStorage(tmp_path)
    request = light_request().model_copy(update={"modes": {LutMode.COLOR_TEMP}})
    storage.create(snapshot(SessionState.RUNNING), request)
    output = storage.artifact_directory("a1b2-c3d4", "LCT010")
    output.mkdir()
    (output / "color_temp.csv").write_text(f"bri,mired,watt\n{brightness},{mired},1.0\n", encoding="utf-8")

    assert storage.can_resume("a1b2-c3d4") is resumable
    recovered = storage.load_current()
    assert recovered is not None
    assert recovered.state == (SessionState.RESUMABLE if resumable else SessionState.FAILED)


def test_running_session_becomes_resumable_after_restart(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(SessionState.RUNNING), light_request())
    output = storage.artifact_directory("a1b2-c3d4", "LCT010")
    output.mkdir()
    (output / "brightness.csv").write_text("bri,watt\n2,1.0\n", encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.RESUMABLE


@pytest.mark.parametrize("tail", ["128,", "128,4.2", "128,\nbroken\n", "128,nan\n"])
def test_incomplete_csv_tail_does_not_block_resume_or_get_repaired_by_storage(tmp_path: Path, tail: str) -> None:
    storage = SessionStorage(tmp_path)
    current = snapshot(SessionState.RUNNING)
    storage.create(current, light_request())
    output = storage.artifact_directory(current.id, "LCT010")
    output.mkdir()
    path = output / "brightness.csv"
    path.write_text("bri,watt\n1,0.45\n" + tail)
    original = path.read_bytes()

    assert storage.can_resume(current.id)
    recovered = storage.load_current()

    assert recovered is not None
    assert recovered.state == SessionState.RESUMABLE
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "state",
    [
        SessionState.VALIDATING,
        SessionState.READY,
        SessionState.AWAITING_CONFIRMATION,
        SessionState.RUNNING,
        SessionState.CANCELLING,
    ],
)
def test_every_orphaned_nonterminal_session_is_recovered(tmp_path: Path, state: SessionState) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(state), light_request())

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.FAILED
    assert "App stopped" in str(loaded.error)


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "bri,watt\n",
        "wrong,watt\n1,1.0\n",
        "bri,watt\n1,",
        "bri,watt\n1,1.0",
        "bri,watt\n999,1.0\n",
        "bri,watt\n999,1.0\n128,",
    ],
)
def test_interrupted_session_without_compatible_complete_row_fails(tmp_path: Path, contents: str) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(SessionState.RUNNING), light_request())
    output = storage.artifact_directory("a1b2-c3d4", "LCT010")
    output.mkdir()
    (output / "brightness.csv").write_text(contents, encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.FAILED
    assert not SessionStorage(tmp_path).can_resume(loaded.id)


def test_storage_recognizes_only_existing_complex_profile_recordings_as_analysable(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    request = RecorderMeasurementRequest(
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.GENERIC,
        tracked_entity_ids=("switch.device",),
        power_meter=DummyPowerMeterSpec(),
    )
    storage.create(snapshot(SessionState.COMPLETED), request)

    assert not storage.can_analyse("missing-session")
    assert not storage.can_analyse("a1b2-c3d4")

    output = storage.artifact_directory("a1b2-c3d4", request.model_id)
    output.mkdir()
    (output / "record.jsonl").write_text("recording", encoding="utf-8")

    assert storage.can_analyse("a1b2-c3d4")


def test_file_path_rejects_traversal(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())

    with pytest.raises(ValueError, match="Path escapes session output directory"):
        storage.file_path("a1b2-c3d4", "../../secret")


def test_effect_output_is_recognized_as_resumable(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    request = light_request().model_copy(update={"modes": {LutMode.EFFECT}})
    storage.create(snapshot(SessionState.RUNNING), request)
    output = storage.artifact_directory("a1b2-c3d4", "LCT010")
    output.mkdir()
    (output / "effect.csv").write_text("effect,bri,watt\nnightlight,205,3.0\n", encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.RESUMABLE


def test_effect_output_off_the_measurement_grid_is_not_resumable(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    request = light_request().model_copy(update={"modes": {LutMode.EFFECT}})
    storage.create(snapshot(SessionState.RUNNING), request)
    output = storage.artifact_directory("a1b2-c3d4", "LCT010")
    output.mkdir()
    # bri=200 is not produced by the effect brightness grid, so the runner could not resume it.
    (output / "effect.csv").write_text("effect,bri,watt\nnightlight,200,3.0\n", encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.FAILED


def test_settings_recover_from_corrupt_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    storage = SessionStorage(tmp_path)
    (tmp_path / "settings.json").write_text("not json")

    with caplog.at_level(logging.WARNING, logger="measure"):
        settings = storage.load_settings()

    assert settings.default_power_entity_id is None
    assert "using defaults" in caplog.text


def test_storage_persists_shelly_credentials_privately(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)

    storage.save_shelly_credentials(ShellyCredentials(password="device-password"))  # noqa: S106

    credential_path = tmp_path / "shelly_credentials.json"
    assert storage.load_shelly_credentials() == ShellyCredentials(password="device-password")  # noqa: S106
    assert credential_path.stat().st_mode & 0o777 == 0o600
    assert not (tmp_path / "settings.json").exists()

    storage.clear_shelly_credentials()
    assert storage.load_shelly_credentials() is None
    assert not credential_path.exists()


def test_storage_round_trips_global_and_session_dummy_load_calibration(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())
    calibration = DummyLoadCalibration(
        description="40 W incandescent bulb",
        resistance=1322.5,
        calibrated_at="2026-07-16T12:00:00Z",
        power_meter_fingerprint="meter-fingerprint",
    )

    storage.save_dummy_load_calibration(calibration)
    storage.save_session_dummy_load_calibration("a1b2-c3d4", calibration)

    assert storage.load_dummy_load_calibration() == calibration
    assert storage.load_session_dummy_load_calibration("a1b2-c3d4") == calibration


def test_contribution_state_recovers_interrupted_submission(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    preview = ContributionPreviewResponse(
        session_id="a1b2-c3d4",
        title="Add profile",
        body="Body",
        eligible=True,
        manufacturer_name="Signify",
        manufacturer_directory="signify",
        model_id="LCT010",
        product_name="Hue lamp",
        contributor="measure-user",
        files=[],
        commit_message="feat(profile): add signify LCT010",
        pr_title="Add signify LCT010 power profile",
        pr_body="Body",
        branch_name="powercalc-profile-signify-lct010",
    )
    storage.save_contribution_status(
        ContributionStatus(
            state=ContributionState.SUBMITTING,
            session_id="a1b2-c3d4",
            preview=preview,
            updated_at="2026-07-12T12:00:00Z",
        ),
    )

    status = ContributionApiCoordinator(storage).status()

    assert status.state == ContributionState.FAILED
    assert status.session_id == "a1b2-c3d4"
    assert status.error == "App stopped during contribution submission; preview can be submitted again"


def test_storage_ignores_invalid_dummy_load_calibration(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    storage = SessionStorage(tmp_path)
    (tmp_path / "dummy_load_calibration.json").write_text('{"resistance": -1}', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="measure"):
        calibration = storage.load_dummy_load_calibration()

    assert calibration is None
    assert "invalid dummy-load calibration" in caplog.text
