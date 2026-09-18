from measure.cli.const import (
    QUESTION_CHARGING_DEVICE_TYPE,
    QUESTION_DURATION,
    QUESTION_ENTITY_ID,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODE,
    QUESTION_POWERMETER_ENTITY_ID,
    QUESTION_VOLTAGEMETER_ENTITY_ID,
)
from measure.cli.request_adapter import request_from_answers
from measure.const import MeasureType
from measure.controller.charging.const import ChargingControllerType, ChargingDeviceType
from measure.controller.charging.spec import HassChargingControllerSpec
from measure.controller.fan.const import FanControllerType
from measure.controller.fan.spec import HassFanControllerSpec
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.light.spec import HassLightControllerSpec, HueLightControllerSpec
from measure.controller.media.const import MediaControllerType
from measure.controller.media.spec import HassMediaControllerSpec
from measure.powermeter.const import OwonOwh98xxChannelType, PowerMeterType
from measure.powermeter.spec import HassPowerMeterSpec, ShellyPowerMeterSpec, TuyaPowerMeterSpec
from measure.request import ResumePolicy
import pytest

from tests.conftest import MockConfigFactory


@pytest.mark.parametrize(
    "meter_type,settings,expected",
    [
        pytest.param(PowerMeterType.KASA, {"kasa_device_ip": "192.0.2.10"}, {"device_ip": "192.0.2.10"}, id="kasa"),
        pytest.param(PowerMeterType.MANUAL, {}, {}, id="manual"),
        pytest.param(
            PowerMeterType.MYSTROM, {"mystrom_device_ip": "192.0.2.11"}, {"device_ip": "192.0.2.11"}, id="mystrom"
        ),
        pytest.param(PowerMeterType.OCR, {}, {}, id="ocr-selection"),
        pytest.param(
            PowerMeterType.TASMOTA, {"tasmota_device_ip": "192.0.2.12"}, {"device_ip": "192.0.2.12"}, id="tasmota"
        ),
        pytest.param(
            PowerMeterType.OWON_OWH98XX,
            {
                "serial_port": "/dev/ttyUSB0",
                "serial_baudrate": 19200,
                "owon_owh98xx_channel": OwonOwh98xxChannelType.CHANNEL2,
            },
            {"port": "/dev/ttyUSB0", "baudrate": 19200, "timeout": 5.0, "channel": OwonOwh98xxChannelType.CHANNEL2},
            id="owon",
        ),
    ],
)
def test_meter_configuration_is_preserved_in_request(
    mock_config_factory: MockConfigFactory,
    meter_type: PowerMeterType,
    settings: dict[str, object],
    expected: dict[str, object],
) -> None:
    environment = mock_config_factory({"selected_power_meter": meter_type, **settings})

    request = request_from_answers(MeasureType.AVERAGE, {QUESTION_DURATION: 60}, environment)

    assert request.power_meter.model_dump() == {"type": meter_type, **expected}


@pytest.mark.parametrize("voltage_entity_id", [None, "", "sensor.voltage"])
def test_home_assistant_meter_preserves_voltage_and_update_settings(
    mock_config_factory: MockConfigFactory, voltage_entity_id: str | None
) -> None:
    environment = mock_config_factory(
        {"selected_power_meter": PowerMeterType.HASS, "hass_call_update_entity_service": True}
    )

    request = request_from_answers(
        MeasureType.AVERAGE,
        {
            QUESTION_DURATION: 60,
            QUESTION_POWERMETER_ENTITY_ID: "sensor.power",
            QUESTION_VOLTAGEMETER_ENTITY_ID: voltage_entity_id,
        },
        environment,
    )

    assert request.power_meter == HassPowerMeterSpec(
        entity_id="sensor.power", voltage_entity_id=voltage_entity_id or None, call_update_entity=True
    )


@pytest.mark.parametrize("entity_id", [None, ""])
def test_missing_required_meter_answer_is_rejected(
    mock_config_factory: MockConfigFactory, entity_id: str | None
) -> None:
    environment = mock_config_factory({"selected_power_meter": PowerMeterType.HASS})

    with pytest.raises(ValueError, match="Missing required CLI answer: powermeter_entity_id"):
        request_from_answers(
            MeasureType.AVERAGE, {QUESTION_DURATION: 60, QUESTION_POWERMETER_ENTITY_ID: entity_id}, environment
        )


def test_home_assistant_light_controller_preserves_transition_time(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory(
        {"selected_light_controller": LightControllerType.HASS, "light_transition_time": 2}
    )

    request = request_from_answers(
        MeasureType.LIGHT,
        {QUESTION_MODE: [LutMode.BRIGHTNESS], QUESTION_ENTITY_ID: "light.test", QUESTION_MEASURE_DEVICE: "Test meter"},
        environment,
    )

    assert request.controller == HassLightControllerSpec(entity_id="light.test", transition_time=2)


def test_home_assistant_speaker_controller_preserves_streaming_choice(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory({"selected_media_controller": MediaControllerType.HASS})

    request = request_from_answers(
        MeasureType.SPEAKER, {QUESTION_ENTITY_ID: "media_player.test", "disable_streaming": True}, environment
    )

    assert request.controller == HassMediaControllerSpec(entity_id="media_player.test")
    assert request.disable_streaming is True


def test_home_assistant_fan_controller_uses_selected_entity(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory({"selected_fan_controller": FanControllerType.HASS})

    request = request_from_answers(MeasureType.FAN, {QUESTION_ENTITY_ID: "fan.test"}, environment)

    assert request.controller == HassFanControllerSpec(entity_id="fan.test")


@pytest.mark.parametrize(
    "device_type,entity_id",
    [
        pytest.param(ChargingDeviceType.VACUUM_ROBOT, "vacuum.test", id="vacuum"),
        pytest.param(ChargingDeviceType.LAWN_MOWER_ROBOT, "lawn_mower.test", id="lawn-mower"),
    ],
)
def test_home_assistant_charging_controller_uses_selected_device_type(
    mock_config_factory: MockConfigFactory, device_type: ChargingDeviceType, entity_id: str
) -> None:
    environment = mock_config_factory({"selected_charging_controller": ChargingControllerType.HASS})

    request = request_from_answers(
        MeasureType.CHARGING, {QUESTION_ENTITY_ID: entity_id, QUESTION_CHARGING_DEVICE_TYPE: device_type}, environment
    )

    assert request.controller == HassChargingControllerSpec(entity_id=entity_id)
    assert request.charging_device_type == device_type


def test_resume_without_model_id_starts_new_measurement(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory({"resume": True})

    request = request_from_answers(MeasureType.AVERAGE, {QUESTION_DURATION: 60}, environment)

    assert request.resume_policy == ResumePolicy.NEW


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


def test_shelly_password_stays_in_cli_config(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory()
    environment.selected_power_meter = PowerMeterType.SHELLY
    environment.shelly_ip = "192.0.2.30"
    environment.shelly_username = "measurement"
    environment.shelly_password = "device-password"  # noqa: S105
    environment.shelly_timeout = 10

    request = request_from_answers(MeasureType.AVERAGE, {QUESTION_DURATION: 60}, environment)

    assert request.power_meter == ShellyPowerMeterSpec(
        device_ip="192.0.2.30",
        username="measurement",
        timeout=10,
    )
    assert "device-password" not in request.model_dump_json()


def test_cli_resume_setting_becomes_request_policy(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory()
    environment.resume = True

    request = request_from_answers(
        MeasureType.AVERAGE,
        {QUESTION_DURATION: 60, "model_id": "existing-run"},
        environment,
    )

    assert request.resume_policy == ResumePolicy.RESUME
