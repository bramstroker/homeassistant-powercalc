import os

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER,
    CalculationStrategy,
)
from custom_components.powercalc.errors import ModelNotSupported, UnsupportedMode
from custom_components.powercalc.power_profile.light_model import DeviceType, LightModel


async def test_load_lut_profile_from_custom_directory(hass: HomeAssistant):
    light_model = LightModel(
        hass, "signify", "LCA001", get_test_profile_dir("signify-LCA001")
    )
    assert light_model.supported_modes == [CalculationStrategy.LUT]
    assert light_model.manufacturer == "signify"
    assert light_model.model == "LCA001"
    assert light_model.is_mode_supported(CalculationStrategy.LUT)
    assert not light_model.is_mode_supported(CalculationStrategy.FIXED)
    assert light_model.device_type == DeviceType.LIGHT
    assert light_model.name == "Hue White and Color Ambiance A19 E26/E27 (Gen 5)"


async def test_load_fixed_profile(hass: HomeAssistant):
    light_model = LightModel(hass, "dummy", "dummy", get_test_profile_dir("fixed"))
    assert light_model.supported_modes == [CalculationStrategy.FIXED]
    assert light_model.standby_power == 0.5
    assert light_model.fixed_mode_config == {CONF_POWER: 50}

    with pytest.raises(UnsupportedMode):
        light_model.linear_mode_config


async def test_load_linear_profile(hass: HomeAssistant):
    light_model = LightModel(hass, "dummy", "dummy", get_test_profile_dir("linear"))
    assert light_model.supported_modes == [CalculationStrategy.LINEAR]
    assert light_model.standby_power == 0.5
    assert light_model.linear_mode_config == {CONF_MIN_POWER: 10, CONF_MAX_POWER: 30}

    with pytest.raises(UnsupportedMode):
        light_model.fixed_mode_config


async def test_load_linked_profile(hass: HomeAssistant):
    light_model = LightModel(
        hass, "signify", "LCA007", get_test_profile_dir("linked_profile")
    )
    assert light_model.supported_modes == [CalculationStrategy.LUT]
    assert light_model.manufacturer == "signify"
    assert light_model.model == "LCA007"
    assert light_model.name == "Linked profile"


async def test_load_sub_lut(hass: HomeAssistant):
    light_model = LightModel(hass, "yeelight", "YLDL01YL/ambilight", None)
    assert light_model.supported_modes == [CalculationStrategy.LUT]
    assert light_model.manufacturer == "yeelight"
    assert light_model.model == "YLDL01YL"
    assert light_model.name == "Yeelight YLDL01YL Downlight"
    assert light_model._lut_subdirectory == "ambilight"
    assert light_model.is_additional_configuration_required == True


async def test_error_loading_model_manifest(hass: HomeAssistant):
    with pytest.raises(ModelNotSupported):
        LightModel(
            hass,
            "dummy_manufacturer",
            "dummy_model",
            get_test_profile_dir("no-model-json"),
        )


def get_test_profile_dir(sub_dir: str) -> str:
    return os.path.join(
        os.path.dirname(__file__), "../testing_config/powercalc_profiles", sub_dir
    )
