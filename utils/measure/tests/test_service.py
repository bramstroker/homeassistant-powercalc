from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import DummyLightControllerSpec, HassLightControllerSpec
from measure.ha_app.service import MeasurementService, _redact
from measure.ha_app.session import SessionControl, SessionEventType
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec
from measure.request import LightMeasurementRequest


def test_service_runs_light_measurement_without_terminal(tmp_path: Path) -> None:
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(entity_id="sensor.test_power"),
        generate_model=False,
        gzip=False,
        parameters={"sleep_time": 0, "brightness_step": 100},
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
    assert any(event.type == SessionEventType.LOG for event in progress)


def test_service_uses_dummy_power_meter_when_enabled(tmp_path: Path) -> None:
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=DummyLightControllerSpec(),
        power_meter=DummyPowerMeterSpec(),
        generate_model=False,
        gzip=False,
        parameters={"sleep_time": 0, "brightness_step": 100},
    )
    control = SessionControl()

    hass_power_meter = MagicMock()
    with (
        patch("measure.assembler.HassPowerMeter", hass_power_meter),
        patch("measure.assembler.HassLightController", return_value=DummyLightController()),
    ):
        result = MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token")).run(
            request,
            control,
            tmp_path,
        )

    hass_power_meter.assert_not_called()
    assert result.model_json_data["device_type"] == "light"


def test_sensitive_values_are_redacted_from_session_messages() -> None:
    assert _redact("Authorization: Bearer secret-token", ("secret-token",)) == "Authorization: Bearer [REDACTED]"
