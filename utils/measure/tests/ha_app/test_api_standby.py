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
