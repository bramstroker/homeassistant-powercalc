from __future__ import annotations

from measure.cli.request_adapter import request_from_answers
from measure.const import PARAMETER_LIMITS, QUESTION_ENTITY_ID, QUESTION_MEASURE_DEVICE, MeasureType
from measure.controller.light.const import LightControllerType, LutMode
from measure.powermeter.const import PowerMeterType
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import (
    _BASE_PARAMETER_FIELDS,
    _LIGHT_PARAMETER_FIELDS,
    AverageMeasurementRequest,
    DummyLoadCalibrationRequest,
    DummyLoadReuseRequest,
    LightMeasurementRequest,
    RecorderMeasurementRequest,
    parse_measurement_request,
)
from measure.runner.const import QUESTION_EXPORT_FILENAME, QUESTION_MODE
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


def test_request_round_trip_preserves_typed_input() -> None:
    request = LightMeasurementRequest.model_validate(
        valid_request()
        | {
            "parameters": {"sleep_time": 0.5, "sample_count": 3},
            "dummy_load": {"mode": "reuse", "description": "60 W incandescent bulb", "resistance": 812.4},
        },
    )

    restored = parse_measurement_request(request.model_dump(mode="json"))

    assert restored == request
    assert isinstance(restored.dummy_load, DummyLoadReuseRequest)


def test_request_accepts_dummy_load_calibration() -> None:
    request = LightMeasurementRequest.model_validate(
        valid_request() | {"dummy_load": {"mode": "calibrate", "description": "60 W incandescent bulb"}},
    )

    assert request.dummy_load == DummyLoadCalibrationRequest(description="60 W incandescent bulb")


@pytest.mark.parametrize(
    "payload",
    [
        valid_request() | {"measure_type": "light"},
        {"measure_type": "average"},
        {"measure_type": "recorder"},
        {"measure_type": "speaker", "controller": {"type": "dummy"}},
        {
            "measure_type": "charging",
            "controller": {"type": "dummy"},
            "charging_device_type": "vacuum_robot",
        },
        {"measure_type": "fan", "controller": {"type": "dummy"}},
    ],
)
def test_all_measurement_types_accept_dummy_load(payload: dict[str, object]) -> None:
    request = parse_measurement_request(
        payload
        | {
            "power_meter": {
                "type": "hass",
                "entity_id": "sensor.test_power",
                "voltage_entity_id": "sensor.test_voltage",
            },
            "dummy_load": {
                "mode": "reuse",
                "description": "60 W incandescent bulb",
                "resistance": 812.4,
            },
        },
    )

    assert request.dummy_load == DummyLoadReuseRequest(
        description="60 W incandescent bulb",
        resistance=812.4,
    )


def test_request_normalizes_and_requires_dummy_load_description() -> None:
    assert DummyLoadCalibrationRequest(description="  reference load  ").description == "reference load"
    with pytest.raises(ValidationError, match="description"):
        DummyLoadCalibrationRequest(description=" ")


@pytest.mark.parametrize("resistance", [0, -1])
def test_request_rejects_non_positive_dummy_load_resistance(resistance: float) -> None:
    payload = valid_request() | {
        "dummy_load": {
            "mode": "reuse",
            "description": "60 W incandescent bulb",
            "resistance": resistance,
        },
    }
    with pytest.raises(ValidationError, match="resistance"):
        LightMeasurementRequest.model_validate(payload)


def test_request_rejects_dummy_load_with_synthetic_power_meter() -> None:
    power_meter = DummyPowerMeterSpec()
    dummy_load = DummyLoadCalibrationRequest(description="test load")
    with pytest.raises(ValidationError, match="synthetic"):
        AverageMeasurementRequest(power_meter=power_meter, dummy_load=dummy_load)


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
    power_meter = DummyPowerMeterSpec()

    with pytest.raises(ValidationError):
        RecorderMeasurementRequest(
            power_meter=power_meter,
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

    assert request.parameters.sleep_time == pytest.approx(0.25)


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"sleep_time_sample": -1}, "sleep_time_sample"),
        ({"max_retries": 101}, "max_retries"),
        ({"max_nudges": 21}, "max_nudges"),
        ({"min_brightness": 0}, "min_brightness"),
        ({"min_sat": 0}, "min_sat"),
        ({"max_hue": 65_536}, "max_hue"),
        ({"bri_bri_steps": 0}, "bri_bri_steps"),
        ({"ct_bri_steps": 11}, "ct_bri_steps"),
        ({"ct_mired_steps": 11}, "ct_mired_steps"),
        ({"hs_hue_steps": 65_536}, "hs_hue_steps"),
        ({"measure_time_effect": 10, "measure_time_effect_min": 20}, "measure_time_effect_min"),
        ({"min_sat": 200, "max_sat": 50}, "min_sat must not exceed max_sat"),
        ({"min_hue": 500, "max_hue": 100}, "min_hue must not exceed max_hue"),
    ],
)
def test_request_rejects_invalid_exposed_tuning(parameters: dict[str, int], message: str) -> None:
    payload = valid_request() | {"parameters": parameters}

    with pytest.raises(ValidationError, match=message):
        LightMeasurementRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("power_meter", "accepted"),
    [
        ({"type": "manual"}, True),
        ({"type": "hass", "entity_id": "sensor.test_power"}, False),
    ],
)
def test_manual_power_meter_allows_coarser_ct_grid(power_meter: dict[str, str], accepted: bool) -> None:
    payload = valid_request() | {
        "power_meter": power_meter,
        "parameters": {"ct_bri_steps": 15, "ct_mired_steps": 50},
    }

    if accepted:
        request = LightMeasurementRequest.model_validate(payload)
        assert request.parameters.ct_bri_steps == 15
        assert request.parameters.ct_mired_steps == 50
    else:
        with pytest.raises(ValidationError, match="ct_bri_steps"):
            LightMeasurementRequest.model_validate(payload)


def test_parameter_limits_cover_exactly_the_validated_fields() -> None:
    assert set(_BASE_PARAMETER_FIELDS) | set(_LIGHT_PARAMETER_FIELDS) == set(PARAMETER_LIMITS)
