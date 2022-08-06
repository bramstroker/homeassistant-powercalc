import os

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER,
    CalculationStrategy,
)
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.errors import ModelNotSupported, UnsupportedMode
from custom_components.powercalc.power_profile.power_profile import DeviceType, PowerProfile


async def test_load_lut_profile_from_custom_directory(hass: HomeAssistant):
    power_profile = ProfileLibrary.factory(hass).get_profile(
        ModelInfo("signify", "LCA001"),
        get_test_profile_dir("signify-LCA001")
    )
    assert power_profile.supported_modes == [CalculationStrategy.LUT]
    assert power_profile.manufacturer == "signify"
    assert power_profile.model == "LCA001"
    assert power_profile.is_mode_supported(CalculationStrategy.LUT)
    assert not power_profile.is_mode_supported(CalculationStrategy.FIXED)
    assert power_profile.device_type == DeviceType.LIGHT
    assert power_profile.name == "Hue White and Color Ambiance A19 E26/E27 (Gen 5)"


async def test_load_fixed_profile(hass: HomeAssistant):
    power_profile = ProfileLibrary.factory(hass).get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("fixed")
    )
    assert power_profile.supported_modes == [CalculationStrategy.FIXED]
    assert power_profile.standby_power == 0.5
    assert power_profile.fixed_mode_config == {CONF_POWER: 50}

    with pytest.raises(UnsupportedMode):
        power_profile.linear_mode_config


async def test_load_linear_profile(hass: HomeAssistant):
    power_profile = ProfileLibrary.factory(hass).get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("linear")
    )
    assert power_profile.supported_modes == [CalculationStrategy.LINEAR]
    assert power_profile.standby_power == 0.5
    assert power_profile.linear_mode_config == {CONF_MIN_POWER: 10, CONF_MAX_POWER: 30}

    with pytest.raises(UnsupportedMode):
        power_profile.fixed_mode_config


async def test_load_linked_profile(hass: HomeAssistant):
    power_profile = ProfileLibrary.factory(hass).get_profile(
        ModelInfo("signify", "LCA007"),
        get_test_profile_dir("linked_profile")
    )
    assert power_profile.supported_modes == [CalculationStrategy.LUT]
    assert power_profile.manufacturer == "signify"
    assert power_profile.model == "LCA007"
    assert power_profile.name == "Linked profile"


async def test_load_sub_lut(hass: HomeAssistant):
    power_profile = ProfileLibrary.factory(hass).get_profile(
        ModelInfo("yeelight", "YLDL01YL/ambilight")
    )
    assert power_profile.supported_modes == [CalculationStrategy.LUT]
    assert power_profile.manufacturer == "yeelight"
    assert power_profile.model == "YLDL01YL"
    assert power_profile.name == "Yeelight YLDL01YL Downlight"
    assert power_profile.sub_profile == "ambilight"
    assert power_profile.is_additional_configuration_required == True


def get_test_profile_dir(sub_dir: str) -> str:
    return os.path.join(
        os.path.dirname(__file__), "../testing_config/powercalc_profiles", sub_dir
    )
