from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from measure.assembler import MeasurementAssembler
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.charging.hass import HassChargingController
from measure.controller.charging.spec import HassChargingControllerSpec
from measure.controller.fan.hass import HassFanController
from measure.controller.fan.spec import DummyFanControllerSpec, HassFanControllerSpec
from measure.controller.light.spec import (
    DummyLightControllerSpec,
    HassLightControllerSpec,
    HassMultiLightControllerSpec,
    HueLightControllerSpec,
)
from measure.controller.media.hass import HassMediaController
from measure.controller.media.spec import HassMediaControllerSpec
from measure.home_assistant.client import HomeAssistantEntityData, HomeAssistantManager
from measure.powermeter.const import OwonOwh98xxChannelType
from measure.powermeter.credentials import TapoCredentials
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.spec import (
    DummyPowerMeterSpec,
    HassPowerMeterSpec,
    KasaPowerMeterSpec,
    ManualPowerMeterSpec,
    MyStromPowerMeterSpec,
    OcrPowerMeterSpec,
    OwonOwh98xxPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
    TasmotaPowerMeterSpec,
    TuyaPowerMeterSpec,
)
from measure.request import (
    AverageMeasurementRequest,
    ChargingMeasurementRequest,
    DummyLoadReuseRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    RecorderMeasurementRequest,
    SpeakerMeasurementRequest,
)
from measure.runner.average import AverageRunner
from measure.runner.charging import ChargingRunner
from measure.runner.fan import FanRunner
from measure.runner.interaction import RunInteraction
from measure.runner.light.runner import LightRunner
from measure.runner.recorder import RecorderEntityState, RecorderRunner
from measure.runner.speaker import SpeakerRunner
from pydantic import ValidationError
import pytest


def _assembler(
    *,
    home_assistant: HomeAssistantManager | None = None,
    tuya_device_key: str | None = None,
    shelly_password: str | None = None,
) -> MeasurementAssembler:
    return MeasurementAssembler(
        MagicMock(spec=RunInteraction),
        home_assistant=home_assistant,
        tuya_device_key=tuya_device_key,
        shelly_password=shelly_password,
    )


@pytest.mark.parametrize(
    "spec,constructor,arguments",
    [
        (MyStromPowerMeterSpec(device_ip="192.0.2.10"), "measure.assembler.MyStromPowerMeter", ["192.0.2.10"]),
        (TasmotaPowerMeterSpec(device_ip="192.0.2.20"), "measure.assembler.TasmotaPowerMeter", ["192.0.2.20"]),
        (ManualPowerMeterSpec(), "measure.assembler.ManualPowerMeter", []),
        (OcrPowerMeterSpec(), "measure.assembler.OcrPowerMeter", []),
    ],
)
def test_assembler_constructs_selected_meter(spec: PowerMeterSpec, constructor: str, arguments: list[object]) -> None:
    with patch(constructor) as meter:
        result = _assembler().create_power_meter(spec)

    assert result is meter.return_value
    meter.assert_called_once_with(*arguments)


def test_assembler_passes_serial_meter_settings() -> None:
    spec = OwonOwh98xxPowerMeterSpec(
        port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=2.5,
        channel=OwonOwh98xxChannelType.CHANNEL1,
    )
    with patch("measure.powermeter.serial_scpi.OwonOwh98xxPowerMeter") as meter:
        result = _assembler().create_power_meter(spec)

    assert result is meter.return_value
    meter.assert_called_once_with("/dev/ttyUSB0", 9600, 2.5, OwonOwh98xxChannelType.CHANNEL1)


def test_assembler_passes_tapo_credentials() -> None:
    credentials = TapoCredentials(username="user@example.com", password="device-password")  # noqa: S106
    assembler = MeasurementAssembler(MagicMock(spec=RunInteraction), kasa_credentials=credentials)

    with patch("measure.powermeter.kasa.KasaPowerMeter") as meter:
        result = assembler.create_power_meter(KasaPowerMeterSpec(device_ip="192.0.2.30"))

    assert result is meter.return_value
    meter.assert_called_once_with("192.0.2.30", credentials=credentials)


def test_assembler_requires_tuya_key_before_creating_device() -> None:
    spec = TuyaPowerMeterSpec(device_id="device-id", device_ip="192.0.2.10")
    with (
        patch("measure.powermeter.tuya.TuyaPowerMeter") as meter,
        pytest.raises(PowerMeterError, match="key is required"),
    ):
        _assembler().create_power_meter(spec)

    meter.assert_not_called()


def test_assembler_requires_home_assistant_for_entity_meter() -> None:
    with pytest.raises(ValueError, match="Home Assistant runtime connection is required"):
        _assembler().create_power_meter(HassPowerMeterSpec(entity_id="sensor.power"))


@pytest.mark.parametrize(
    "measurement_request, runner_type",
    [
        (
            LightMeasurementRequest(
                model_id="light",
                product_name="Light",
                measure_device="Meter",
                power_meter=DummyPowerMeterSpec(),
                controller=DummyLightControllerSpec(),
            ),
            LightRunner,
        ),
        (
            FanMeasurementRequest(
                power_meter=DummyPowerMeterSpec(),
                controller=DummyFanControllerSpec(),
            ),
            FanRunner,
        ),
        (AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()), AverageRunner),
    ],
)
def test_assembler_builds_runner_from_request(measurement_request, runner_type) -> None:  # noqa: ANN001
    prepared = _assembler().assemble(measurement_request)

    assert isinstance(prepared.runner, runner_type)
    assert prepared.request is measurement_request


def test_assembler_builds_recorder_state_reader_from_home_assistant() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = HomeAssistantEntityData(
        entities={
            "vacuum": SimpleNamespace(
                entities={
                    "robot": SimpleNamespace(
                        entity_id="vacuum.robot", state=SimpleNamespace(state="cleaning", attributes={})
                    ),
                }
            )
        },
        entity_registry=[
            SimpleNamespace(
                entity_id="vacuum.robot",
                device_id="robot-device",
                platform="dreame_vacuum",
                translation_key="vacuum",
            )
        ],
        device_registry=[],
    )
    home_assistant.get_states.return_value = (
        SimpleNamespace(entity_id="vacuum.robot", state="cleaning", attributes={"battery_level": 42}),
        SimpleNamespace(entity_id="light.unrelated", state="on", attributes={}),
    )
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("vacuum.robot",),
    )

    prepared = _assembler(home_assistant=home_assistant).assemble(request)

    assert isinstance(prepared.runner, RecorderRunner)
    assert prepared.runner.entity_state_reader is not None
    assert prepared.runner.recording_context is not None
    assert prepared.runner.recording_context.entities[0].translation_key == "vacuum"
    assert prepared.runner.recording_context.entities[0].integration == "dreame_vacuum"
    assert prepared.runner.entity_state_reader(("vacuum.robot",)) == {
        "vacuum.robot": RecorderEntityState(state="cleaning", attributes={"battery_level": 42}),
    }
    # One dump covers every tracked entity, however many there are.
    home_assistant.get_states.assert_called_once_with()
    assert prepared.runner.entity_state_reader(("sensor.missing",)) == {}
    home_assistant.get_entity_data.assert_called_once_with()


def test_assembler_applies_typed_home_assistant_configuration_at_construction() -> None:
    request = LightMeasurementRequest(
        model_id="light",
        product_name="Light",
        measure_device="Meter",
        power_meter=HassPowerMeterSpec(
            entity_id="sensor.power",
            voltage_entity_id="sensor.voltage",
            call_update_entity=True,
        ),
        controller=HassLightControllerSpec(entity_id="light.test", transition_time=2),
    )
    home_assistant = HomeAssistantManager("ws://127.0.0.1/api/websocket", "token")

    with (
        patch("measure.assembler.HassPowerMeter") as power_meter,
        patch("measure.assembler.HassLightController") as light_controller,
    ):
        power_meter.return_value.has_voltage_support.return_value = False
        _assembler(home_assistant=home_assistant).assemble(request)

    power_meter.assert_called_once_with(
        home_assistant,
        True,
        entity_id="sensor.power",
        voltage_entity_id="sensor.voltage",
        wait=ANY,
    )
    light_controller.assert_called_once_with(
        home_assistant,
        2,
        entity_ids=["light.test"],
        wait=ANY,
    )


def test_assembler_builds_multi_light_controller() -> None:
    request = LightMeasurementRequest(
        model_id="light",
        product_name="Light",
        measure_device="Meter",
        power_meter=DummyPowerMeterSpec(),
        controller=HassMultiLightControllerSpec(entity_ids=["light.one", "light.two"], transition_time=2),
        multiple_light_count=2,
    )
    home_assistant = MagicMock(spec=HomeAssistantManager)

    with patch("measure.assembler.HassLightController") as controller:
        _assembler(home_assistant=home_assistant).assemble(request)

    controller.assert_called_once_with(home_assistant, 2, entity_ids=["light.one", "light.two"], wait=ANY)


@pytest.mark.parametrize("target", ["light:7", "group:3"])
def test_assembler_passes_hue_bridge_and_target(target: str) -> None:
    spec = HueLightControllerSpec(bridge_ip="192.0.2.40", light=target)

    with patch("measure.controller.light.hue.HueLightController") as controller:
        result = _assembler().create_light_controller(spec)

    assert result is controller.return_value
    controller.assert_called_once_with("192.0.2.40", light=target)


def test_assembler_wires_home_assistant_speaker_controller() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    request = SpeakerMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        controller=HassMediaControllerSpec(entity_id="media_player.speaker"),
    )

    prepared = _assembler(home_assistant=home_assistant).assemble(request)

    assert isinstance(prepared.runner, SpeakerRunner)
    controller = prepared.runner.media_controller
    assert isinstance(controller, HassMediaController)
    controller.set_volume(35)
    home_assistant.trigger_service.assert_called_once_with(
        "media_player",
        "volume_set",
        entity_id="media_player.speaker",
        volume_level=0.35,
    )


def test_assembler_wires_home_assistant_charging_controller() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity.return_value.state.state = "docked"
    request = ChargingMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        controller=HassChargingControllerSpec(entity_id="vacuum.robot"),
        charging_device_type=ChargingDeviceType.VACUUM_ROBOT,
    )

    prepared = _assembler(home_assistant=home_assistant).assemble(request)

    assert isinstance(prepared.runner, ChargingRunner)
    controller = prepared.runner.controller
    assert isinstance(controller, HassChargingController)
    assert controller.is_charging() is True
    home_assistant.get_entity.assert_called_once_with(entity_id="vacuum.robot")


def test_assembler_wires_home_assistant_fan_controller() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    request = FanMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        controller=HassFanControllerSpec(entity_id="fan.desk"),
    )

    prepared = _assembler(home_assistant=home_assistant).assemble(request)

    assert isinstance(prepared.runner, FanRunner)
    controller = prepared.runner.fan_controller
    assert isinstance(controller, HassFanController)
    controller.set_percentage(50)
    home_assistant.trigger_service.assert_called_once_with(
        "fan",
        "set_percentage",
        percentage=50,
        entity_id="fan.desk",
    )


def test_assembler_reads_tuya_key_from_cli_config_dependency() -> None:
    request = AverageMeasurementRequest(
        power_meter=TuyaPowerMeterSpec(
            device_id="device-id",
            device_ip="192.0.2.20",
            version="3.4",
        ),
    )

    with patch("measure.powermeter.tuya.TuyaPowerMeter") as power_meter:
        power_meter.return_value.has_voltage_support.return_value = False
        _assembler(tuya_device_key="device-key").assemble(request)

    power_meter.assert_called_once_with("device-id", "192.0.2.20", "device-key", "3.4")


def test_assembler_reads_shelly_password_from_secret_dependency() -> None:
    request = AverageMeasurementRequest(
        power_meter=ShellyPowerMeterSpec(
            device_ip="192.0.2.30",
            username="measurement",
            timeout=10,
        ),
    )

    with patch("measure.assembler.ShellyPowerMeter") as power_meter:
        power_meter.return_value.has_voltage_support.return_value = False
        _assembler(shelly_password="device-password").assemble(request)  # noqa: S106

    power_meter.assert_called_once_with(
        "192.0.2.30",
        10,
        username="measurement",
        password="device-password",  # noqa: S106
    )


def test_assembler_rejects_a_controller_for_the_wrong_measurement_type() -> None:
    power_meter = DummyPowerMeterSpec()
    controller = DummyLightControllerSpec()

    with pytest.raises(ValidationError):
        FanMeasurementRequest(
            power_meter=power_meter,
            controller=controller,
        )


def test_assembler_adds_dummy_load_preparation_and_corrected_sample_callback() -> None:
    on_sample = MagicMock()
    request = AverageMeasurementRequest.model_construct(
        power_meter=DummyPowerMeterSpec(),
        dummy_load=DummyLoadReuseRequest(description="test load", resistance=42.5),
    )

    prepared = MeasurementAssembler(
        MagicMock(spec=RunInteraction),
        on_sample=on_sample,
    ).assemble(request)

    assert len(prepared.preparations) == 1
