from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

from measure.assembler import MeasurementAssembler
from measure.controller.fan.spec import DummyFanControllerSpec
from measure.controller.light.spec import DummyLightControllerSpec, HassLightControllerSpec
from measure.execution import RunInteraction
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, TuyaPowerMeterSpec
from measure.request import (
    AverageMeasurementRequest,
    DummyLoadReuseRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
)
from measure.runner.average import AverageRunner
from measure.runner.fan import FanRunner
from measure.runner.light import LightRunner
from pydantic import ValidationError
import pytest


def _assembler(
    *,
    home_assistant: HomeAssistantManager | None = None,
    tuya_device_key: str | None = None,
    power_meter_decorator: MagicMock | None = None,
) -> MeasurementAssembler:
    return MeasurementAssembler(
        MagicMock(spec=RunInteraction),
        home_assistant=home_assistant,
        tuya_device_key=tuya_device_key,
        power_meter_decorator=power_meter_decorator,
    )


@pytest.mark.parametrize(
    ("measurement_request", "runner_type"),
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
        entity_id="light.test",
        wait=ANY,
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


def test_assembler_applies_power_meter_decorator() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    decorator = MagicMock(side_effect=lambda meter: meter)

    _assembler(power_meter_decorator=decorator).assemble(request)

    decorator.assert_called_once()


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
