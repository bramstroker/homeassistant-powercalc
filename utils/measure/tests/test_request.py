from __future__ import annotations

from measure.cli.request_adapter import request_from_answers
from measure.const import QUESTION_ENTITY_ID, QUESTION_MEASURE_DEVICE, MeasureType
from measure.controller.charging.spec import HassChargingControllerSpec
from measure.controller.fan.spec import HassFanControllerSpec
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.light.spec import HassLightControllerSpec
from measure.controller.media.spec import HassMediaControllerSpec
from measure.powermeter.const import PowerMeterType
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import (
    AverageMeasurementRequest,
    BaseMeasurementRequest,
    ChargingMeasurementRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    RecorderMeasurementRequest,
    SpeakerMeasurementRequest,
    parse_measurement_request,
)
from measure.runner.const import QUESTION_EXPORT_FILENAME, QUESTION_MODE
from measure.tuning import MeasurementParameters
from pydantic import ValidationError
import pytest

from tests.conftest import MockConfigFactory


def valid_request() -> dict[str, object]:
    return {
        "model_id": "LCT010",
        "product_name": "Test light",
        "measure_device": "Test meter",
        "controller": {"type": "hass", "entity_id": "light.test"},
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
    }


def test_request_converts_to_domain_values() -> None:
    model = LightMeasurementRequest.model_validate(valid_request())

    request = model

    assert request.model_id == "LCT010"
    assert request.modes == {LutMode.BRIGHTNESS}


def test_request_uses_measurement_settings_defaults() -> None:
    request = LightMeasurementRequest.model_validate(valid_request())

    assert request.parameters == MeasurementParameters()


def test_request_round_trip_preserves_resolved_adapters_and_parameters() -> None:
    request = LightMeasurementRequest.model_validate(
        valid_request() | {"parameters": {"sleep_time": 0.5, "sample_count": 3}},
    )

    restored = parse_measurement_request(request.model_dump(mode="json"))

    assert restored == request


def test_requests_share_a_validated_base() -> None:
    light_request = LightMeasurementRequest.model_validate(valid_request())
    run_request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=60)

    assert isinstance(light_request, BaseMeasurementRequest)
    assert light_request.measure_type == MeasureType.LIGHT
    assert light_request.controller == HassLightControllerSpec(entity_id="light.test")
    assert isinstance(run_request, BaseMeasurementRequest)
    assert run_request.measure_type == MeasureType.AVERAGE
    assert run_request.duration == 60


@pytest.mark.parametrize(
    ("model", "measure_type"),
    [
        (AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=60), MeasureType.AVERAGE),
        (
            RecorderMeasurementRequest(
                power_meter=DummyPowerMeterSpec(),
                export_filename="record.csv",
            ),
            MeasureType.RECORDER,
        ),
        (
            SpeakerMeasurementRequest(
                power_meter=DummyPowerMeterSpec(),
                controller=HassMediaControllerSpec(entity_id="media_player.test"),
            ),
            MeasureType.SPEAKER,
        ),
        (
            ChargingMeasurementRequest(
                power_meter=DummyPowerMeterSpec(),
                controller=HassChargingControllerSpec(entity_id="vacuum.test"),
                charging_device_type="vacuum_robot",
            ),
            MeasureType.CHARGING,
        ),
        (
            FanMeasurementRequest(
                power_meter=DummyPowerMeterSpec(),
                controller=HassFanControllerSpec(entity_id="fan.test"),
            ),
            MeasureType.FAN,
        ),
    ],
)
def test_concrete_requests_have_their_measure_type(
    model: MeasurementRequest,
    measure_type: MeasureType,
) -> None:
    request = model

    assert request.measure_type == measure_type


def test_cli_request_contains_only_resolved_measurement_input(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory()
    environment.selected_power_meter = PowerMeterType.DUMMY
    environment.selected_light_controller = LightControllerType.DUMMY
    answers = {
        QUESTION_ENTITY_ID: "light.hue_test",
        QUESTION_MEASURE_DEVICE: "Test meter",
        QUESTION_MODE: {LutMode.BRIGHTNESS},
        "hue_group": "Kitchen",
    }

    request = request_from_answers(MeasureType.LIGHT, answers, environment)

    assert request.power_meter.type == PowerMeterType.DUMMY
    assert "hue_group" not in request.model_dump()


@pytest.mark.parametrize("model_id", ["../secret", "/unsafe/file", "a/b", ".."])
def test_request_rejects_unsafe_model_id(model_id: str) -> None:
    payload = valid_request() | {"model_id": model_id}

    with pytest.raises(ValidationError):
        LightMeasurementRequest.model_validate(payload)


def test_request_rejects_unknown_fields() -> None:
    payload = valid_request() | {"token": "secret"}

    with pytest.raises(ValidationError):
        LightMeasurementRequest.model_validate(payload)


@pytest.mark.parametrize(
    "export_filename",
    ["../record.csv", "folder/record.csv", r"folder\record.csv", "..", "bad:name.csv"],
)
def test_recorder_request_rejects_unsafe_export_filename(export_filename: str) -> None:
    with pytest.raises(ValidationError):
        RecorderMeasurementRequest(
            power_meter=DummyPowerMeterSpec(),
            export_filename=export_filename,
        )


def test_cli_recorder_request_rejects_unsafe_export_filename(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory()
    environment.selected_power_meter = PowerMeterType.DUMMY
    with pytest.raises(ValueError, match="without directory components"):
        request_from_answers(
            MeasureType.RECORDER,
            {QUESTION_EXPORT_FILENAME: "../record.csv"},
            environment,
        )


def test_request_preserves_subsecond_sleep_time() -> None:
    request = AverageMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        parameters={"sleep_time": 0.25},
    )

    assert request.parameters.sleep_time == 0.25


def test_measurement_parameters_default_to_historical_native_light_grid() -> None:
    parameters = MeasurementParameters()

    assert parameters.bri_bri_steps == 1
    assert parameters.ct_bri_steps == 5
    assert parameters.ct_mired_steps == 10
    assert parameters.hs_bri_steps == 32
    assert parameters.hs_hue_steps == 2731
    assert parameters.hs_sat_steps == 32


def test_measurement_parameters_preserve_explicit_native_steps() -> None:
    parameters = MeasurementParameters(
        ct_bri_steps=11,
        ct_mired_steps=12,
        bri_bri_steps=13,
        hs_bri_steps=14,
        hs_hue_steps=15,
        hs_sat_steps=16,
    )

    assert parameters.ct_bri_steps == 11
    assert parameters.ct_mired_steps == 12
    assert parameters.bri_bri_steps == 13
    assert parameters.hs_bri_steps == 14
    assert parameters.hs_hue_steps == 15
    assert parameters.hs_sat_steps == 16


@pytest.mark.parametrize("field", ["brightness_step", "color_temp_step", "hue_step", "saturation_step"])
def test_light_request_rejects_removed_percentage_step_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        LightMeasurementRequest.model_validate(valid_request() | {"parameters": {field: 5}})


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"sleep_time_sample": -1}, "sleep_time_sample"),
        ({"max_retries": 101}, "max_retries"),
        ({"max_nudges": 21}, "max_nudges"),
        ({"min_brightness": 0}, "min_brightness"),
        ({"bri_bri_steps": 0}, "bri_bri_steps"),
        ({"ct_mired_steps": 501}, "ct_mired_steps"),
        ({"hs_hue_steps": 65_536}, "hs_hue_steps"),
        ({"measure_time_effect": 10, "measure_time_effect_min": 20}, "measure_time_effect_min"),
    ],
)
def test_request_rejects_invalid_exposed_tuning(parameters: dict[str, int], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        LightMeasurementRequest.model_validate(valid_request() | {"parameters": parameters})
