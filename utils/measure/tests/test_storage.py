from __future__ import annotations

from pathlib import Path

from measure.request import LightMeasurementRequestModel
from measure.session import SessionSnapshot, SessionState, utc_now
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


def snapshot(state: SessionState = SessionState.READY) -> SessionSnapshot:
    now = utc_now()
    return SessionSnapshot(id="a1b2-c3d4", state=state, created_at=now, updated_at=now)


def test_storage_round_trips_current_session(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), request_model())

    loaded = storage.load_current()

    assert loaded is not None
    assert loaded.id == "a1b2-c3d4"
    assert storage.load_request(loaded.id).model_id == "LCT010"


def test_running_session_becomes_resumable_after_restart(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(SessionState.RUNNING), request_model())
    output = storage.output_directory("a1b2-c3d4") / "LCT010"
    output.mkdir()
    (output / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.RESUMABLE


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "bri,watt\n",
        "wrong,watt\n1,1.0\n",
        "bri,watt\n1,",
        "bri,watt\n999,1.0\n",
        "bri,watt\n2,1.0\n",
    ],
)
def test_interrupted_session_without_compatible_complete_row_fails(tmp_path: Path, contents: str) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(SessionState.RUNNING), request_model())
    output = storage.output_directory("a1b2-c3d4") / "LCT010"
    output.mkdir()
    (output / "brightness.csv").write_text(contents, encoding="utf-8")

    loaded = SessionStorage(tmp_path).load_current()

    assert loaded is not None
    assert loaded.state == SessionState.FAILED
    assert not SessionStorage(tmp_path).can_resume(loaded.id)


def test_file_path_rejects_traversal(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    storage.create(snapshot(), request_model())

    with pytest.raises(ValueError):
        storage.file_path("a1b2-c3d4", "../../secret")


def test_settings_default_when_absent(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)

    assert storage.load_settings().default_power_entity_id is None


def test_settings_round_trip(tmp_path: Path) -> None:
    from measure.settings import AppSettings

    storage = SessionStorage(tmp_path)
    storage.save_settings(AppSettings(default_power_entity_id="sensor.plug_power"))

    assert storage.load_settings().default_power_entity_id == "sensor.plug_power"


def test_settings_recover_from_corrupt_file(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    (tmp_path / "settings.json").write_text("not json")

    assert storage.load_settings().default_power_entity_id is None
