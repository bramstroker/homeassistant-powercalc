from typing import Any

from measure.ha_app.library_catalog import StandbyCatalog
from measure.profile.models import ProfileMetadata
from measure.profile.standby import StandbyEstimate, estimate_standby_power, is_valid_standby_power
from pydantic import ValidationError
import pytest
import requests


def model(model_id: str, power: object, **overrides: object) -> dict[str, Any]:
    return {
        "id": model_id,
        "device_type": "light",
        "standby_power": power,
        "device_specs": {"connectivity": ["zigbee", "bluetooth"]},
        **overrides,
    }


def library(models: list[object]) -> dict[str, Any]:
    return {"manufacturers": [{"name": "signify", "full_name": "Signify", "aliases": ["Philips"], "models": models}]}


def test_estimate_uses_manufacturer_alias_and_median_of_distinct_measured_lights() -> None:
    models = [model("a", 0.2), model("b", 0.8), model("c", 0.4), model("d", 0.6)]
    models.extend(
        [
            model("a", 0.9),
            model("estimated", 5, standby_power_estimated=True),
            model("template", "{{ 1 }}"),
            model("zero", 0),
            model("nan", float("nan")),
            model("plug", 5, device_type="smart_switch"),
            model("wifi", 3, device_specs={"connectivity": ["wifi"]}),
            model("missing-specs", 3, device_specs=None),
            model("invalid-specs", 3, device_specs={"connectivity": [42]}),
            model("", 2),
            None,
        ]
    )
    estimate = StandbyCatalog(loader=lambda: library(models)).estimate("Philips", ["bluetooth", "zigbee"])
    assert estimate.power_w == 0.5
    assert estimate.basis == "manufacturer"
    assert estimate.profile_count == 4


def test_estimate_broadens_to_matching_connectivity_only_with_three_profiles() -> None:
    data = library([model("a", 0.1), model("b", 0.2)])
    assert estimate_standby_power(data, "New brand", ["zigbee", "bluetooth"]) == StandbyEstimate()
    data["manufacturers"].append({"name": "Other", "models": [model("a", 0.6)]})
    estimate = estimate_standby_power(data, "Signify", ["zigbee", "bluetooth"])
    assert estimate.power_w == 0.2
    assert estimate.basis == "connectivity"
    assert estimate.profile_count == 3


@pytest.mark.parametrize("data", [None, {}, {"manufacturers": None}, {"manufacturers": [None, {}]}])
def test_estimate_handles_missing_library_data(data: object) -> None:
    assert estimate_standby_power(data, "Brand", ["wifi"]) == StandbyEstimate()


def test_unknown_connectivity_and_library_failure_use_documented_fallback() -> None:
    def unavailable() -> object:
        raise requests.ConnectionError("offline")

    catalog = StandbyCatalog(loader=unavailable)
    assert catalog.estimate("Brand", []) == StandbyEstimate()
    assert catalog.estimate("Brand", ["wifi"]) == StandbyEstimate()
    assert estimate_standby_power(library([]), "Brand", []) == StandbyEstimate()


@pytest.mark.parametrize("value", [0, -1, 0.049, True, "0.4", float("nan"), float("inf")])
def test_invalid_standby_is_rejected(value: object) -> None:
    assert not is_valid_standby_power(value)
    with pytest.raises(ValidationError):
        ProfileMetadata.model_validate({"manufacturer": "Brand", "model_id": "test", "standby_power": value})


def test_boundary_value_is_accepted() -> None:
    assert is_valid_standby_power(0.05)
    metadata = ProfileMetadata(manufacturer="Brand", model_id="test", standby_power=0.05)
    assert metadata.standby_power == 0.05
