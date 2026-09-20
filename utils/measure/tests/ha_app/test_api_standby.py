from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.ha_app.coordinator import SessionConflictError
from measure.ha_app.light_probe import StandbyProbeResult, StandbyProbeStatus
from measure.ha_app.session import SessionSnapshot, SessionState
from measure.request import DummyLoadCalibrationRequest, DummyLoadReuseRequest, MeasurementRequest
from pydantic import TypeAdapter
import pytest

from tests.ha_app.test_standby import standby_request


def create_session(
    client: TestClient, request: MeasurementRequest, state: SessionState = SessionState.COMPLETED
) -> None:
    context = client.app.state.context
    context.developer_mode = True
    now = "2026-09-19T10:00:00Z"
    context.storage.create(SessionSnapshot(id="standby", state=state, created_at=now, updated_at=now), request)
    context.standby_measurement = MagicMock()
    context.standby_measurement.measure.return_value = StandbyProbeResult(StandbyProbeStatus.MEASURED, 0.7)


@pytest.mark.parametrize("kind", ["light", "speaker", "fan", "charging", "recorder", "average"])
def test_standby_retries_completed_session_without_modifying_it(app_client: TestClient, kind: str) -> None:
    request = standby_request(kind)
    create_session(app_client, request)
    context = app_client.app.state.context
    original = context.storage.load_snapshot("standby")
    response = app_client.post("/api/sessions/standby/standby", json={"confirmed": True})
    assert response.status_code == 200
    assert response.json() == {"status": "measured", "power_w": 0.7}
    context.standby_measurement.measure.assert_called_once_with(request, None)
    assert context.storage.load_snapshot("standby") == original
    assert context.storage.load_request("standby") == request


@pytest.mark.parametrize("body", [{}, {"confirmed": False}])
def test_confirmation_required(app_client: TestClient, body: dict[str, bool]) -> None:
    create_session(app_client, standby_request())
    assert app_client.post("/api/sessions/standby/standby", json=body).status_code == 400
    app_client.app.state.context.standby_measurement.measure.assert_not_called()


def test_missing_and_incomplete_session(app_client: TestClient) -> None:
    assert app_client.post("/api/sessions/missing/standby", json={"confirmed": True}).status_code == 404
    create_session(app_client, standby_request(), SessionState.FAILED)
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True}).status_code == 409
    app_client.app.state.context.standby_measurement.measure.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("power_meter", {"type": "manual"}),
        ("power_meter", {"type": "ocr"}),
    ],
)
def test_app_supported_meter_required(app_client: TestClient, field: str, value: dict[str, str]) -> None:
    payload = standby_request().model_dump()
    payload[field] = value
    create_session(app_client, TypeAdapter(MeasurementRequest).validate_python(payload))
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True}).status_code == 422


@pytest.mark.parametrize("field", ["controller", "power_meter"])
def test_dummy_hardware_allowed_for_testing(app_client: TestClient, field: str) -> None:
    payload = standby_request().model_dump()
    payload[field] = {"type": "dummy"}
    request = TypeAdapter(MeasurementRequest).validate_python(payload)
    create_session(app_client, request)
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True}).status_code == 200
    app_client.app.state.context.standby_measurement.measure.assert_called_once_with(request, None)


@pytest.mark.parametrize("mode", ["saved", "reuse", "missing", "mismatch"])
def test_dummy_load_calibration(app_client: TestClient, mode: str) -> None:
    dummy_load = (
        DummyLoadReuseRequest(description="Bulb", resistance=2300)
        if mode == "reuse"
        else DummyLoadCalibrationRequest(description="Bulb")
    )
    request = standby_request().model_copy(update={"dummy_load": dummy_load})
    create_session(app_client, request)
    context = app_client.app.state.context
    if mode in ["saved", "mismatch"]:
        context.storage.save_session_dummy_load_calibration(
            "standby",
            DummyLoadCalibration(
                description="Bulb",
                resistance=2400,
                calibrated_at="2026-09-19T10:00:00Z",
                power_meter_fingerprint=power_meter_fingerprint(request.power_meter) if mode == "saved" else "other",
            ),
        )
    response = app_client.post("/api/sessions/standby/standby", json={"confirmed": True})
    assert response.status_code == (200 if mode in ["saved", "reuse"] else 422)
    if mode in ["saved", "reuse"]:
        context.standby_measurement.measure.assert_called_once_with(request, 2400 if mode == "saved" else 2300)
    else:
        context.standby_measurement.measure.assert_not_called()


def test_device_reservation_blocks_conflicting_actions_and_releases(app_client: TestClient) -> None:
    request = standby_request()
    create_session(app_client, request)
    context = app_client.app.state.context
    with context.coordinator.reserve_devices():
        assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True}).status_code == 409
        assert app_client.post("/api/preflight", json=request.model_dump(mode="json")).status_code == 409
        assert app_client.delete("/api/sessions/standby").status_code == 409
        for action in [
            lambda: context.coordinator.start(request),
            lambda: context.coordinator.resume("standby"),
            lambda: context.coordinator.record_more("standby"),
        ]:
            with pytest.raises(SessionConflictError, match="device check"):
                action()
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True}).status_code == 200


def test_changed_setup_preserves_original_and_records_effective_setup(app_client: TestClient) -> None:
    import json

    original = standby_request()
    create_session(app_client, original)
    context = app_client.app.state.context
    setup = original.model_dump(mode="json")
    setup.update(controller={"type": "hass", "entity_id": "light.test"}, multiple_light_count=2)
    setup["parameters"].update(sleep_standby=20, sample_count=5, sleep_time_sample=2)
    response = app_client.post("/api/sessions/standby/standby", json={"confirmed": True, "setup": setup})
    assert response.status_code == 200
    effective = context.standby_measurement.measure.call_args.args[0]
    assert effective.controlled_entity_ids == ["light.test"]
    assert effective.multiple_light_count == 2
    assert effective.parameters.sleep_standby == 20
    assert context.storage.load_request("standby") == original
    record = json.loads((context.storage.session_directory("standby") / "standby_retry.json").read_text())
    assert record["setup"]["multiple_light_count"] == 2
    assert record["result"]["power_w"] == 0.7


@pytest.mark.parametrize("outcome", ["unavailable", "error"])
def test_failed_retry_preserves_existing_record(app_client: TestClient, outcome: str) -> None:
    from measure.powermeter.errors import PowerMeterError

    create_session(app_client, standby_request())
    context = app_client.app.state.context
    path = context.storage.session_directory("standby") / "standby_retry.json"
    path.write_text("original")
    if outcome == "unavailable":
        context.standby_measurement.measure.return_value = StandbyProbeResult(StandbyProbeStatus.UNAVAILABLE)
    else:
        context.standby_measurement.measure.side_effect = PowerMeterError("offline")
    app_client.post("/api/sessions/standby/standby", json={"confirmed": True})
    assert path.read_text() == "original"


@pytest.mark.parametrize("mismatch", [None, "meter", "description", "resistance", "missing"])
def test_changed_setup_requires_compatible_calibration(app_client: TestClient, mismatch: str | None) -> None:
    original = standby_request()
    create_session(app_client, original)
    context = app_client.app.state.context
    calibration = DummyLoadCalibration(
        description="Heater",
        resistance=2400,
        calibrated_at="2026-09-20T10:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(original.power_meter),
    )
    if mismatch != "missing":
        context.storage.save_dummy_load_calibration(calibration)
    setup = original.model_dump(mode="json")
    setup["dummy_load"] = {
        "mode": "reuse",
        "description": "Other" if mismatch == "description" else "Heater",
        "resistance": 2500 if mismatch == "resistance" else 2400,
    }
    if mismatch == "meter":
        setup["power_meter"]["entity_id"] = "sensor.other"
    response = app_client.post("/api/sessions/standby/standby", json={"confirmed": True, "setup": setup})
    assert response.status_code == (200 if mismatch is None else 422)
    if mismatch:
        context.standby_measurement.measure.assert_not_called()
    else:
        assert context.standby_measurement.measure.call_args.args[1] == 2400


def test_calibration_is_separate_from_completed_session(app_client: TestClient) -> None:
    original = standby_request()
    create_session(app_client, original)
    context = app_client.app.state.context
    calibration = DummyLoadCalibration(
        description="Heater",
        resistance=2400,
        calibrated_at="2026-09-20T10:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(original.power_meter),
    )
    context.standby_measurement.calibrate.return_value = calibration
    setup = original.model_dump(mode="json")
    setup["dummy_load"] = {"mode": "calibrate", "description": "Heater"}
    response = app_client.post("/api/sessions/standby/standby/calibrate", json={"confirmed": True, "setup": setup})
    assert response.status_code == 202
    assert wait_calibration(app_client)["status"] == "completed"
    assert context.storage.load_dummy_load_calibration() == calibration
    assert context.storage.load_session_dummy_load_calibration("standby") is None
    assert context.storage.load_request("standby") == original
    context.standby_measurement.measure.assert_not_called()


@pytest.mark.parametrize(
    "field,value", [("multiple_light_count", 0), ("controller", {"type": "hass", "entity_id": "bad"})]
)
def test_invalid_setup_does_not_measure(app_client: TestClient, field: str, value: object) -> None:
    original = standby_request()
    create_session(app_client, original)
    setup = original.model_dump(mode="json")
    setup[field] = value
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True, "setup": setup}).status_code == 400
    app_client.app.state.context.standby_measurement.measure.assert_not_called()


def test_original_reuse_setup_still_works_without_saved_calibration(app_client: TestClient) -> None:
    original = standby_request().model_copy(
        update={"dummy_load": DummyLoadReuseRequest(description="Bulb", resistance=2300)}
    )
    create_session(app_client, original)
    response = app_client.post(
        "/api/sessions/standby/standby", json={"confirmed": True, "setup": original.model_dump(mode="json")}
    )
    assert response.status_code == 200
    app_client.app.state.context.standby_measurement.measure.assert_called_once_with(original, 2300)


def test_non_light_cannot_override_setup(app_client: TestClient) -> None:
    create_session(app_client, standby_request("fan"))
    response = app_client.post(
        "/api/sessions/standby/standby", json={"confirmed": True, "setup": standby_request().model_dump(mode="json")}
    )
    assert response.status_code == 422
    app_client.app.state.context.standby_measurement.measure.assert_not_called()


@pytest.mark.parametrize("problem", ["incomplete", "missing_load", "busy", "voltage"])
def test_calibration_failure_preserves_session(app_client: TestClient, problem: str) -> None:
    from measure.powermeter.errors import UnsupportedFeatureError

    original = standby_request()
    create_session(app_client, original, SessionState.FAILED if problem == "incomplete" else SessionState.COMPLETED)
    context = app_client.app.state.context
    setup = original.model_dump(mode="json")
    if problem != "missing_load":
        setup["dummy_load"] = {"mode": "calibrate", "description": "Bulb"}
    context.standby_measurement.calibrate.side_effect = UnsupportedFeatureError("Voltage unsupported")
    body = {"confirmed": True, "setup": setup}
    if problem == "busy":
        with context.coordinator.reserve_devices():
            response = app_client.post("/api/sessions/standby/standby/calibrate", json=body)
    else:
        response = app_client.post("/api/sessions/standby/standby/calibrate", json=body)
    assert response.status_code == (409 if problem in ["incomplete", "busy"] else 202 if problem == "voltage" else 422)
    if problem == "voltage":
        assert wait_calibration(app_client)["status"] == "failed"
    assert context.storage.load_dummy_load_calibration() is None
    assert context.storage.load_request("standby") == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("controller", {"type": "hass", "entity_id": "light.kitchn"}),
        ("power_meter", {"type": "hass", "entity_id": "sensor.missing"}),
        ("power_meter", {"type": "hass", "entity_id": "sensor.test_power", "voltage_entity_id": "sensor.missing"}),
    ],
)
@pytest.mark.parametrize("action", ["", "/calibrate"])
def test_retry_rejects_unknown_entities(app_client: TestClient, field: str, value: object, action: str) -> None:
    request = standby_request()
    create_session(app_client, request)
    setup = request.model_dump(mode="json")
    setup[field] = value
    response = app_client.post(f"/api/sessions/standby/standby{action}", json={"confirmed": True, "setup": setup})
    assert response.status_code == 422
    context = app_client.app.state.context
    context.standby_measurement.measure.assert_not_called()
    context.standby_measurement.calibrate.assert_not_called()


def test_record_write_failure_preserves_successful_reading(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_session(app_client, standby_request())
    monkeypatch.setattr("measure.ha_app.routes.sessions.write_json_atomic", MagicMock(side_effect=OSError("Disk full")))
    response = app_client.post("/api/sessions/standby/standby", json={"confirmed": True})
    assert response.status_code == 200
    assert response.json()["power_w"] == 0.7


def test_edited_dummy_setup_does_not_need_ha_entities(app_client: TestClient) -> None:
    setup = standby_request().model_dump(mode="json")
    setup.update(controller={"type": "dummy"}, power_meter={"type": "dummy"})
    create_session(app_client, TypeAdapter(MeasurementRequest).validate_python(setup))
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True, "setup": setup}).status_code == 200


def wait_calibration(client: TestClient) -> dict[str, object]:
    import time

    for _ in range(200):
        response = client.get("/api/sessions/standby/standby/calibrate")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in ["running", "cancelling"]:
            return job
        time.sleep(0.005)
    pytest.fail("Calibration did not finish")


def test_background_calibration_survives_requests_and_can_be_cancelled(app_client: TestClient) -> None:
    from threading import Event

    from measure.cancellation import MeasurementCancelledError

    original = standby_request().model_copy(update={"dummy_load": DummyLoadCalibrationRequest(description="Heater")})
    create_session(app_client, original)
    context = app_client.app.state.context
    started = Event()

    def calibrate(request: MeasurementRequest, cancelled: Event) -> None:
        started.set()
        assert cancelled.wait(5)
        raise MeasurementCancelledError("cancelled")

    context.standby_measurement.calibrate.side_effect = calibrate
    assert app_client.get("/api/sessions/standby/standby/calibrate").json() is None
    response = app_client.post("/api/sessions/standby/standby/calibrate", json={"confirmed": True})
    assert response.status_code == 202
    assert started.wait(1)
    job = response.json()
    # The original response has ended, but another request can recover the active operation.
    assert app_client.get("/api/sessions/standby/standby/calibrate").json()["id"] == job["id"]
    assert app_client.post("/api/sessions/standby/standby/calibrate", json={"confirmed": True}).status_code == 409
    assert app_client.post("/api/sessions/standby/standby", json={"confirmed": True}).status_code == 409
    assert app_client.post("/api/sessions/standby/standby/calibrate/wrong/cancel").status_code == 404
    assert app_client.post(f"/api/sessions/standby/standby/calibrate/{job['id']}/cancel").status_code == 200
    assert wait_calibration(app_client)["status"] == "cancelled"
    assert (
        app_client.post(f"/api/sessions/standby/standby/calibrate/{job['id']}/cancel").json()["status"] == "cancelled"
    )
    assert context.storage.load_dummy_load_calibration() is None
    with context.coordinator.reserve_devices():
        pass


@pytest.mark.parametrize("finish", ["cancel_before_save", "shutdown", "save_failure", "thread_failure"])
def test_calibration_cleanup_and_failed_persistence(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch, finish: str
) -> None:
    from threading import Event

    from measure.cancellation import MeasurementCancelledError
    from measure.ha_app.calibration import CalibrationJobs

    original = standby_request().model_copy(update={"dummy_load": DummyLoadCalibrationRequest(description="Heater")})
    create_session(app_client, original)
    context = app_client.app.state.context
    save = MagicMock(side_effect=OSError("Disk full") if finish == "save_failure" else None)
    calibration = DummyLoadCalibration(
        description="Heater", resistance=2400, calibrated_at="today", power_meter_fingerprint="meter"
    )
    started = Event()

    def calibrate(request: MeasurementRequest, cancelled: Event) -> DummyLoadCalibration:
        started.set()
        if finish == "cancel_before_save":
            cancelled.set()
        if finish == "shutdown":
            assert cancelled.wait(5)
            raise MeasurementCancelledError("shutdown")
        return calibration

    jobs = CalibrationJobs(context.coordinator.reserve_devices, calibrate, save)
    context.calibration_jobs = jobs
    if finish == "thread_failure":
        monkeypatch.setattr(
            "measure.ha_app.calibration.Thread.start", MagicMock(side_effect=RuntimeError("cannot start"))
        )
        with pytest.raises(RuntimeError, match="cannot start"):
            jobs.start("standby", original)
        assert jobs.get("standby") is None
    else:
        jobs.start("standby", original)
        assert started.wait(1)
        if finish == "shutdown":
            jobs.shutdown()
        assert wait_calibration(app_client)["status"] == ("failed" if finish == "save_failure" else "cancelled")
        if finish != "save_failure":
            save.assert_not_called()
    with context.coordinator.reserve_devices():
        pass


@pytest.mark.parametrize(
    "adapter",
    [
        {"type": "tuya", "device_id": "device", "device_ip": "192.0.2.1"},
        {"type": "owh98xx", "port": "/dev/ttyUSB0", "baudrate": 9600, "channel": "1"},
        {"type": "dummy"},
        {"type": "hue", "bridge_ip": "192.0.2.1", "light": "1"},
    ],
)
@pytest.mark.parametrize("action", ["", "/calibrate"])
def test_retry_enforces_app_adapter_policy(app_client: TestClient, adapter: dict[str, object], action: str) -> None:
    original = standby_request()
    create_session(app_client, original)
    context = app_client.app.state.context
    context.developer_mode = False
    setup = original.model_dump(mode="json")
    setup["controller" if adapter["type"] == "hue" else "power_meter"] = adapter
    response = app_client.post(f"/api/sessions/standby/standby{action}", json={"confirmed": True, "setup": setup})
    assert response.status_code == 422, response.text
    context.standby_measurement.measure.assert_not_called()
    context.standby_measurement.calibrate.assert_not_called()
