from __future__ import annotations

import json
import logging
from pathlib import Path

from measure.controller.light.const import LutMode
from measure.controller.light.spec import DummyLightControllerSpec
from measure.dummy_load import DummyLoadCalibration
from measure.ha_app.contribution import (
    ContributionCoordinator,
    ContributionPreview,
    ContributionState,
    ContributionStatus,
)
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState, utc_now
from measure.ha_app.storage import SessionStorage
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import LightMeasurementRequest
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


def test_running_session_becomes_resumable_after_restart(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(SessionState.RUNNING), light_request())
    output = storage.artifact_directory("a1b2-c3d4", "LCT010")
    output.mkdir()
    (output / "brightness.csv").write_text("bri,watt\n2,1.0\n", encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.RESUMABLE


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
        "bri,watt\n999,1.0\n",
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


def test_file_path_rejects_traversal(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), light_request())

    with pytest.raises(ValueError):
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
    preview = ContributionPreview(
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

    status = ContributionCoordinator(storage).status()

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
