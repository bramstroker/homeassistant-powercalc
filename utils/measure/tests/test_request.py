from __future__ import annotations

from measure.controller.light.const import LutMode
from measure.request import LightMeasurementRequestModel
from pydantic import ValidationError
import pytest


def valid_request() -> dict[str, object]:
    return {
        "model_id": "LCT010",
        "product_name": "Test light",
        "measure_device": "Test meter",
        "light_entity_id": "light.test",
        "power_entity_id": "sensor.test_power",
    }


def test_request_converts_to_domain_values() -> None:
    model = LightMeasurementRequestModel.model_validate(valid_request())

    request = model.to_domain()

    assert request.model_id == "LCT010"
    assert request.modes == frozenset({LutMode.BRIGHTNESS})


@pytest.mark.parametrize("model_id", ["../secret", "/unsafe/file", "a/b", ".."])
def test_request_rejects_unsafe_model_id(model_id: str) -> None:
    payload = valid_request() | {"model_id": model_id}

    with pytest.raises(ValidationError):
        LightMeasurementRequestModel.model_validate(payload)


def test_request_rejects_unknown_fields() -> None:
    payload = valid_request() | {"token": "secret"}

    with pytest.raises(ValidationError):
        LightMeasurementRequestModel.model_validate(payload)
