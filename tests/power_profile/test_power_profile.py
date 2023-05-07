import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER,
    CalculationStrategy,
)
from custom_components.powercalc.errors import (
    ModelNotSupportedError,
    PowercalcSetupError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.power_profile import (
    DeviceType,
    PowerProfile,
    SubProfileSelector,
)
from tests.common import get_test_profile_dir


async def test_load_lut_profile_from_custom_directory(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("signify", "LCA001"), get_test_profile_dir("signify-LCA001"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "signify"
    assert power_profile.model == "LCA001"
    assert power_profile.is_strategy_supported(CalculationStrategy.LUT)
    assert not power_profile.is_strategy_supported(CalculationStrategy.FIXED)
    assert power_profile.device_type == DeviceType.LIGHT
    assert power_profile.name == "Hue White and Color Ambiance A19 E26/E27 (Gen 5)"


async def test_load_fixed_profile(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("dummy", "dummy"), get_test_profile_dir("fixed"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.FIXED
    assert power_profile.standby_power == 0.5
    assert power_profile.fixed_mode_config == {CONF_POWER: 50}

    with pytest.raises(UnsupportedStrategyError):
        power_profile.linear_mode_config


async def test_load_linear_profile(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("dummy", "dummy"), get_test_profile_dir("linear"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LINEAR
    assert power_profile.standby_power == 0.5
    assert power_profile.linear_mode_config == {CONF_MIN_POWER: 10, CONF_MAX_POWER: 30}

    with pytest.raises(UnsupportedStrategyError):
        power_profile.fixed_mode_config


async def test_load_linked_profile(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("signify", "LCA007"), get_test_profile_dir("linked_profile"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "signify"
    assert power_profile.model == "LCA007"
    assert power_profile.name == "Linked profile"


async def test_load_sub_profile(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("yeelight", "YLDL01YL/ambilight"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "yeelight"
    assert power_profile.model == "YLDL01YL"
    assert power_profile.name == "Yeelight YLDL01YL Downlight"
    assert power_profile.sub_profile == "ambilight"
    assert power_profile.is_additional_configuration_required is False


async def test_load_sub_profile_without_model_json(hass: HomeAssistant):
    """Test if sub profile can be loaded correctly when the sub directories don't have an own model.json"""
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("test", "test/a"), get_test_profile_dir("sub_profile"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "test"
    assert power_profile.model == "test"
    assert power_profile.name == "Test"
    assert power_profile.sub_profile == "a"


async def test_error_when_sub_profile_not_exists(hass: HomeAssistant):
    with pytest.raises(ModelNotSupportedError):
        await ProfileLibrary.factory(hass).get_profile(
            ModelInfo("yeelight", "YLDL01YL/ambilight_boo"),
        )


async def test_unsupported_entity_domain(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("signify", "LCA007"),
    )
    assert power_profile.is_entity_domain_supported(
        SourceEntity("light.test", "test", "light"),
    )
    assert not power_profile.is_entity_domain_supported(
        SourceEntity("switch.test", "test", "switch"),
    )


async def test_sub_profile_attribute_match(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("Test", "Test"),
        get_test_profile_dir("sub_profile_attribute_match"),
    )
    selector = SubProfileSelector(hass, power_profile)
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test", STATE_OFF)
    assert selector.select_sub_profile(state) == "a"

    state = State("light.test", STATE_ON, {"some": "a"})
    assert selector.select_sub_profile(state) == "a"

    state = State("light.test", STATE_ON, {"some": "b"})
    assert selector.select_sub_profile(state) == "b"


async def test_sub_profile_entity_id_match(hass: HomeAssistant):
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("Test", "Test"),
        get_test_profile_dir("sub_profile_entity_id_match"),
    )
    selector = SubProfileSelector(hass, power_profile)
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test_nightlight", STATE_ON)
    assert selector.select_sub_profile(state) == "nightlight"

    state = State("light.test", STATE_ON)
    assert selector.select_sub_profile(state) == "default"


async def test_exception_is_raised_when_invalid_sub_profile_matcher_supplied(
    hass: HomeAssistant,
):
    with pytest.raises(PowercalcSetupError):
        power_profile = PowerProfile(
            hass,
            manufacturer="Foo",
            model="Bar",
            directory=None,
            json_data={
                "sub_profile_select": {
                    "matchers": [{"type": "invalid_type"}],
                    "default": "henkie",
                },
            },
        )
        SubProfileSelector(hass, power_profile)


async def test_selecting_sub_profile_is_ignored(hass: HomeAssistant) -> None:
    """
    For power profiles not supporting sub profiles it should ignore setting the sub profile
    This should not happen anyway
    """
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("dummy", "dummy"), get_test_profile_dir("smart_switch"),
    )

    power_profile.select_sub_profile("foo")
    assert not power_profile.sub_profile


async def test_device_type(hass: HomeAssistant) -> None:
    power_profile = await ProfileLibrary.factory(hass).get_profile(
        ModelInfo("dummy", "dummy"), get_test_profile_dir("media_player"),
    )

    assert power_profile.device_type == DeviceType.SMART_SPEAKER
