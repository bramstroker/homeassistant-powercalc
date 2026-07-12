from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from measure.controller.light.dummy import DummyLightController
from measure.powermeter.const import PowerMeterType
from measure.powermeter.dummy import DummyPowerMeter
from measure.request import LightMeasurementRequestModel
from measure.service import MeasurementService, _redact
from measure.session import SessionControl, SessionEventType


def test_service_runs_light_measurement_without_terminal(tmp_path: Path) -> None:
    request = LightMeasurementRequestModel(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        light_entity_id="light.test",
        power_entity_id="sensor.test_power",
        generate_model=False,
        gzip=False,
        sleep_time=0,
        brightness_step=100,
    ).to_domain()
    progress = []
    control = SessionControl()
    control.subscribe(progress.append)

    with (
        patch("measure.service.HassPowerMeter", return_value=DummyPowerMeter()),
        patch("measure.service.HassLightController", return_value=DummyLightController()),
    ):
        result, export_directory = MeasurementService("https://supervisor/core/api/", "token").run(
            request,
            control,
            tmp_path,
        )

    assert result.model_json_data["device_type"] == "light"
    assert (export_directory / "brightness.csv").is_file()
    progress_events = [event for event in progress if event.type == SessionEventType.PROGRESS]
    assert progress_events[-1].data["completed"] == progress_events[-1].data["total"]
    assert any(event.type == SessionEventType.LOG for event in progress)


def test_service_uses_dummy_power_meter_when_enabled(tmp_path: Path) -> None:
    request = LightMeasurementRequestModel(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        light_entity_id="light.test",
        power_entity_id="sensor.test_power",
        generate_model=False,
        gzip=False,
        sleep_time=0,
        brightness_step=100,
    ).to_domain()
    control = SessionControl()

    hass_power_meter = MagicMock()
    with (
        patch("measure.service.HassPowerMeter", hass_power_meter),
        patch("measure.service.HassLightController", return_value=DummyLightController()),
    ):
        result, _ = MeasurementService(
            "https://supervisor/core/api/",
            "token",
            PowerMeterType.DUMMY,
        ).run(request, control, tmp_path)

    hass_power_meter.assert_not_called()
    assert result.model_json_data["device_type"] == "light"


def test_sensitive_values_are_redacted_from_session_messages() -> None:
    assert _redact("Authorization: Bearer secret-token", ("secret-token",)) == "Authorization: Bearer [REDACTED]"
