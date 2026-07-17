from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import HassLightControllerSpec
from measure.ha_app.service import MeasurementService, SessionDummyLoadCalibrationStore, _redact
from measure.ha_app.session import SessionControl, SessionEventType, SessionSnapshot, SessionState, utc_now
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.spec import HassPowerMeterSpec
from measure.request import DummyLoadCalibrationRequest, LightMeasurementRequest


def test_service_runs_light_measurement_without_terminal(tmp_path: Path) -> None:
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(entity_id="sensor.test_power"),
        generate_model=False,
        gzip=False,
        parameters={"sleep_time": 0, "bri_bri_steps": 255},
    )
    progress = []
    control = SessionControl()
    control.subscribe(progress.append)

    with (
        patch("measure.assembler.HassPowerMeter", return_value=DummyPowerMeter()),
        patch("measure.assembler.HassLightController", return_value=DummyLightController()),
    ):
        result = MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token")).run(
            request,
            control,
            tmp_path,
        )

    assert result.model_json_data["device_type"] == "light"
    assert (tmp_path / request.model_id / "brightness.csv").is_file()
    progress_events = [event for event in progress if event.type == SessionEventType.PROGRESS]
    assert progress_events[-1].data["completed"] == progress_events[-1].data["total"]
    phases = [event.data["message"] for event in progress if event.type == SessionEventType.PHASE]
    assert phases[:2] == ["Preparing measurement devices", "Starting measurement"]
    assert any(message.startswith("Stabilizing light") for message in phases)
    assert any(event.type == SessionEventType.LOG for event in progress)


def test_sensitive_values_are_redacted_from_session_messages() -> None:
    assert _redact("Authorization: Bearer secret-token", ("secret-token",)) == "Authorization: Bearer [REDACTED]"


def test_session_dummy_load_store_persists_for_resume_and_future_sessions(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    now = utc_now()
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(
            entity_id="sensor.test_power",
            voltage_entity_id="sensor.test_voltage",
        ),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )
    storage.create(
        SessionSnapshot(id="a1b2-c3d4", state=SessionState.RUNNING, created_at=now, updated_at=now),
        request,
    )
    store = SessionDummyLoadCalibrationStore(storage, "a1b2-c3d4")

    calibration = store.save(request, 1322.5)

    assert store.load(request) == calibration
    assert storage.load_dummy_load_calibration() == calibration
