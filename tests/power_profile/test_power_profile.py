from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_registry import RegistryEntry

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


async def test_load_lut_profile_from_custom_directory(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("signify", "LCA001"),
        get_test_profile_dir("signify_LCA001"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "signify"
    assert power_profile.model == "LCA001"
    assert power_profile.is_strategy_supported(CalculationStrategy.LUT)
    assert not power_profile.is_strategy_supported(CalculationStrategy.FIXED)
    assert power_profile.device_type == DeviceType.LIGHT
    assert power_profile.name == "Hue White and Color Ambiance A19 E26/E27 (Gen 5)"
    assert not power_profile.aliases


async def test_load_fixed_profile(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("fixed"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.FIXED
    assert power_profile.standby_power == 0.5
    assert power_profile.fixed_config == {CONF_POWER: 50}

    with pytest.raises(UnsupportedStrategyError):
        _ = power_profile.linear_config


async def test_load_linear_profile(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("linear"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LINEAR
    assert power_profile.standby_power == 0.5
    assert power_profile.linear_config == {CONF_MIN_POWER: 10, CONF_MAX_POWER: 30}

    with pytest.raises(UnsupportedStrategyError):
        _ = power_profile.fixed_config


async def test_load_linked_profile(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("signify", "LCA007"),
        get_test_profile_dir("linked_profile"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "signify"
    assert power_profile.model == "LCA007"
    assert power_profile.name == "Linked profile"


async def test_load_sub_profile(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("yeelight", "YLDL01YL/ambilight"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "yeelight"
    assert power_profile.model == "YLDL01YL"
    assert power_profile.name == "Yeelight YLDL01YL Downlight"
    assert power_profile.sub_profile == "ambilight"


async def test_load_sub_profile_without_model_json(hass: HomeAssistant) -> None:
    """Test if sub profile can be loaded correctly when the sub directories don't have an own model.json"""
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("test", "test/a"),
        get_test_profile_dir("sub_profile"),
    )
    assert power_profile.calculation_strategy == CalculationStrategy.LUT
    assert power_profile.manufacturer == "test"
    assert power_profile.model == "test"
    assert power_profile.name == "Test"
    assert power_profile.sub_profile == "a"


async def test_default_calculation_strategy_lut(hass: HomeAssistant) -> None:
    """By default the calculation strategy must be LUT when no strategy is configured"""
    power_profile = PowerProfile(hass, "signify", "LCT010", "", {})
    assert power_profile.calculation_strategy == CalculationStrategy.LUT


async def test_error_when_sub_profile_not_exists(hass: HomeAssistant) -> None:
    with pytest.raises(ModelNotSupportedError):
        library = await ProfileLibrary.factory(hass)
        await library.get_profile(
            ModelInfo("yeelight", "YLDL01YL/ambilight_boo"),
        )


async def test_unsupported_entity_domain(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("signify", "LCA007"),
    )
    assert power_profile.is_entity_domain_supported(
        RegistryEntry(entity_id="light.test", platform="hue", unique_id="1234"),
    )
    assert not power_profile.is_entity_domain_supported(
        RegistryEntry(entity_id="switch.test", platform="bla", unique_id="1234"),
    )


async def test_hue_switch_supported_entity_domain(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("signify", "LOM001"),
    )
    assert power_profile.is_entity_domain_supported(
        RegistryEntry(
            entity_id="light.test",
            unique_id="1234",
            platform="hue",
        ),
    )


async def test_vacuum_entity_domain_supported(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("roborock", "s6_maxv"),
        get_test_profile_dir("vacuum"),
    )
    assert power_profile.is_entity_domain_supported(
        RegistryEntry(
            entity_id="vacuum.test",
            unique_id="1234",
            platform="xiaomi_miio",
        ),
    )


async def test_light_domain_supported_for_smart_switch_device_type(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("smart_switch"),
    )
    assert power_profile.is_entity_domain_supported(
        SourceEntity("light.test", "test", "light"),
    )


async def test_discovery_does_not_break_when_unknown_device_type(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("test", "test"),
        get_test_profile_dir("unknown_device_type"),
    )
    assert not power_profile.is_entity_domain_supported(
        SourceEntity("switch.test", "test", "switch"),
    )


async def test_sub_profile_matcher_attribute(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        get_test_profile_dir("sub_profile_match_attribute"),
    )
    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        SourceEntity(entity_id="light.test", domain="light", object_id="test"),
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test", STATE_OFF)
    assert selector.select_sub_profile(state) == "a"

    state = State("light.test", STATE_ON, {"some": "a"})
    assert selector.select_sub_profile(state) == "a"

    state = State("light.test", STATE_ON, {"some": "b"})
    assert selector.select_sub_profile(state) == "b"


async def test_sub_profile_matcher_entity_id(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        get_test_profile_dir("sub_profile_match_entity_id"),
    )
    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        SourceEntity(entity_id="light.test", domain="light", object_id="test"),
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test_nightlight", STATE_ON)
    assert selector.select_sub_profile(state) == "nightlight"

    state = State("light.test", STATE_ON)
    assert selector.select_sub_profile(state) == "default"


@pytest.mark.parametrize(
    "registry_entry,expected_profile",
    [
        (
            RegistryEntry(
                entity_id="switch.test",
                platform="tasmota",
                unique_id="111",
            ),
            "tasmota",
        ),
        (
            RegistryEntry(
                entity_id="switch.test",
                platform="shelly",
                unique_id="111",
            ),
            "default",
        ),
        (None, "default"),
    ],
)
async def test_sub_profile_matcher_integration(
    hass: HomeAssistant,
    registry_entry: RegistryEntry,
    expected_profile: str | None,
) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        get_test_profile_dir("sub_profile_match_integration"),
    )

    source_entity = SourceEntity(
        entity_id="switch.test",
        domain="switch",
        object_id="test",
        entity_entry=registry_entry,
    )

    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        source_entity,
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("switch.test", STATE_ON)
    assert selector.select_sub_profile(state) == expected_profile


async def test_exception_is_raised_when_invalid_sub_profile_matcher_supplied(
    hass: HomeAssistant,
) -> None:
    with pytest.raises(PowercalcSetupError):
        power_profile = PowerProfile(
            hass,
            manufacturer="Foo",
            model="Bar",
            directory="",
            json_data={
                "sub_profile_select": {
                    "matchers": [{"type": "invalid_type"}],
                    "default": "henkie",
                },
            },
        )
        SubProfileSelector(
            hass,
            power_profile.sub_profile_select,
            SourceEntity(entity_id="light.test", domain="light", object_id="test"),
        )


async def test_selecting_sub_profile_is_ignored(hass: HomeAssistant) -> None:
    """
    For power profiles not supporting sub profiles it should ignore setting the sub profile
    This should not happen anyway
    """
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("smart_switch"),
    )

    await power_profile.select_sub_profile("foo")
    assert not power_profile.sub_profile


async def test_device_type(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("dummy", "dummy"),
        get_test_profile_dir("media_player"),
    )

    assert power_profile.device_type == DeviceType.SMART_SPEAKER


@pytest.mark.parametrize(
    "json_data,expected_result",
    [
        (
            {
                "calculation_strategy": CalculationStrategy.FIXED,
            },
            True,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.LINEAR,
            },
            True,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.COMPOSITE,
                "fields": {
                    "foo": {
                        "label": "Foo",
                        "selector": {"entity": {}},
                    },
                },
            },
            True,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.FIXED,
                "fixed_config": {
                    "power": 50,
                },
            },
            False,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.LINEAR,
                "linear_config": {
                    "min_power": 50,
                    "max_power": 100,
                },
            },
            False,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.MULTI_SWITCH,
                "multi_switch_config": {
                    "power": 0.725,
                    "power_off": 0.225,
                },
            },
            True,
        ),
    ],
)
async def test_needs_user_configuration(hass: HomeAssistant, json_data: dict[str, Any], expected_result: bool) -> None:
    power_profile = PowerProfile(
        hass,
        manufacturer="test",
        model="test",
        directory=get_test_profile_dir("media_player"),
        json_data=json_data,
    )

    assert await power_profile.needs_user_configuration == expected_result


@pytest.mark.parametrize(
    "json_data,expected_result",
    [
        (
            {
                "calculation_strategy": CalculationStrategy.FIXED,
                "fixed_config": {
                    "power": 50,
                },
            },
            False,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.FIXED,
            },
            True,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.FIXED,
                "only_self_usage": True,
            },
            False,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.LINEAR,
                "linear_config": {
                    "min_power": 50,
                    "max_power": 100,
                },
            },
            False,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.LINEAR,
            },
            True,
        ),
        (
            {
                "calculation_strategy": CalculationStrategy.LINEAR,
                "only_self_usage": True,
            },
            False,
        ),
    ],
)
async def test_needs_fixed_power(hass: HomeAssistant, json_data: dict[str, Any], expected_result: bool) -> None:
    power_profile = PowerProfile(
        hass,
        manufacturer="test",
        model="test",
        directory=get_test_profile_dir("smart_switch"),
        json_data=json_data,
    )

    assert await power_profile.needs_user_configuration == expected_result


@pytest.mark.parametrize(
    "test_profile,expected_translation_key",
    [
        (
            "smart_switch",
            "component.powercalc.common.remarks_smart_switch",
        ),
        (
            "smart_switch_with_pm",
            None,
        ),
        (
            "smart_dimmer",
            "component.powercalc.common.remarks_smart_dimmer",
        ),
        (
            "smart_dimmer_with_pm",
            None,
        ),
        (
            "media_player",
            None,
        ),
    ],
)
async def test_discovery_flow_remarks(hass: HomeAssistant, test_profile: str, expected_translation_key: str | None) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("test", "test"),
        get_test_profile_dir(test_profile),
    )

    translations_keys = [
        "component.powercalc.common.remarks_smart_dimmer",
        "component.powercalc.common.remarks_smart_switch",
    ]
    with patch(
        "homeassistant.helpers.translation.async_get_cached_translations",
        return_value={key: key for key in translations_keys},
    ):
        assert power_profile.config_flow_discovery_remarks == expected_translation_key
