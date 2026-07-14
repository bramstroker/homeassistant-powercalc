from __future__ import annotations

from measure.cli.request_adapter import request_from_answers
from measure.const import QUESTION_MEASURE_DEVICE, MeasureType
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.light.spec import HueLightControllerSpec
from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID, PowerMeterType
from measure.powermeter.spec import HassPowerMeterSpec, TuyaPowerMeterSpec
from measure.request import ResumePolicy
from measure.runner.const import QUESTION_DURATION, QUESTION_MODE

from tests.conftest import MockConfigFactory


def test_cli_answers_and_environment_become_one_measurement_request(
    mock_config_factory: MockConfigFactory,
) -> None:
    environment = mock_config_factory()
    environment.selected_light_controller = LightControllerType.HUE
    environment.selected_power_meter = PowerMeterType.HASS
    environment.hue_bridge_ip = "192.0.2.10"
    answers = {
        QUESTION_MEASURE_DEVICE: "Test meter",
        QUESTION_MODE: {LutMode.BRIGHTNESS},
        QUESTION_POWERMETER_ENTITY_ID: "sensor.power",
        "light": "group:12",
    }

    request = request_from_answers(MeasureType.LIGHT, answers, environment)

    assert request.power_meter == HassPowerMeterSpec(entity_id="sensor.power")
    assert request.controller == HueLightControllerSpec(bridge_ip="192.0.2.10", light="group:12")
    assert request.parameters.ct_bri_steps == environment.ct_bri_steps


def test_tuya_key_stays_in_cli_config(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory()
    environment.selected_power_meter = PowerMeterType.TUYA
    environment.tuya_device_id = "device-id"
    environment.tuya_device_ip = "192.0.2.20"
    environment.tuya_device_key = "device-key"
    environment.tuya_device_version = "3.4"

    request = request_from_answers(MeasureType.AVERAGE, {QUESTION_DURATION: 60}, environment)

    assert request.power_meter == TuyaPowerMeterSpec(
        device_id="device-id",
        device_ip="192.0.2.20",
        version="3.4",
    )
    assert "device-key" not in request.model_dump_json()


def test_cli_resume_setting_becomes_request_policy(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory()
    environment.resume = True

    request = request_from_answers(MeasureType.AVERAGE, {QUESTION_DURATION: 60}, environment)

    assert request.resume_policy == ResumePolicy.RESUME
