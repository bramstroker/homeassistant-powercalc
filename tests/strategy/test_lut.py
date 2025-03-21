import logging
from decimal import Decimal

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ColorMode,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import CONF_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.util import color as color_util

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL, CalculationStrategy
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from custom_components.powercalc.strategy.strategy_interface import (
    PowerCalculationStrategyInterface,
)
from tests.common import get_test_profile_dir, run_powercalc_setup
from tests.strategy.common import create_source_entity


async def test_color_temp_lut(hass: HomeAssistant) -> None:
    """Test LUT lookup in color_temp mode"""

    source_entity = create_source_entity(LIGHT_DOMAIN, [ColorMode.COLOR_TEMP])

    strategy = await _create_lut_strategy(hass, "signify", "LCT010", source_entity)
    await strategy.validate_config()

    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(brightness=100, color_temp=300),
        expected_power=2.5,
    )

    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(brightness=144, color_temp=450),
        expected_power=3.01,
    )

    # Out of bound values
    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(brightness=-6, color_temp=170),
        expected_power=2.03,
    )
    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(brightness=300, color_temp=400),
        expected_power=7.34,
    )


async def test_brightness_lut(hass: HomeAssistant) -> None:
    """Test LUT lookup in brightness mode"""

    source_entity = create_source_entity(LIGHT_DOMAIN, [ColorMode.BRIGHTNESS])

    strategy = await _create_lut_strategy(hass, "signify", "LWB010", source_entity)
    await strategy.validate_config()

    await _calculate_and_assert_power(
        strategy,
        state=_create_light_brightness_state(100),
        expected_power=2.05,
    )

    # Out of bounds brightness. Power for bri 255 should be returned and no error
    await _calculate_and_assert_power(
        strategy,
        state=_create_light_brightness_state(450),
        expected_power=9.65,
    )


async def test_hs_lut(hass: HomeAssistant) -> None:
    """Test LUT lookup in HS mode"""

    source_entity = create_source_entity(LIGHT_DOMAIN, [ColorMode.HS])

    strategy = await _create_lut_strategy(hass, "signify", "LCT010", source_entity)
    await strategy.validate_config()

    await _calculate_and_assert_power(
        strategy,
        state=_create_light_hs_state(100, 200, 300),
        expected_power=1.53,
    )


@pytest.mark.parametrize(
    "effect,brightness,expected_power",
    [
        ("Android", 20, 2.08),
        ("Android", 100, 2.73),
        ("Android", 255, 4.00),
        ("Wipe Random", 20, 1.98),
        ("Non existing effect", 100, None),
    ],
)
async def test_effect_lut(hass: HomeAssistant, effect: str, brightness: int, expected_power: float) -> None:
    """Test LUT lookup in effect mode"""
    strategy = await _create_lut_strategy(
        hass,
        "test",
        "test",
        custom_profile_dir=get_test_profile_dir("lut_effect"),
    )
    await _calculate_and_assert_power(
        strategy,
        state=State(
            "light.test",
            STATE_ON,
            {
                ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
                ATTR_COLOR_TEMP_KELVIN: 153,
                ATTR_BRIGHTNESS: brightness,
                ATTR_EFFECT: effect,
            },
        ),
        expected_power=expected_power,
    )


async def test_effect_mode_unsupported(hass: HomeAssistant) -> None:
    """
    Test light is set in effect mode, but effect is not supported by the profile.
    In this case normal LUT for color mode should be used.
    """
    strategy = await _create_lut_strategy(hass, "signify", "LWB010", "light.test")
    await _calculate_and_assert_power(
        strategy,
        state=State(
            "light.test",
            STATE_ON,
            {
                ATTR_COLOR_MODE: ColorMode.BRIGHTNESS,
                ATTR_BRIGHTNESS: 255,
                ATTR_EFFECT: "Test",
            },
        ),
        expected_power=9.65,
    )


async def test_hs_lut_attribute_none(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test error is logged when hs_color attribute is None"""

    caplog.set_level(logging.ERROR)
    source_entity = create_source_entity(LIGHT_DOMAIN, [ColorMode.HS])

    strategy = await _create_lut_strategy(hass, "signify", "LCT010", source_entity)
    await strategy.validate_config()

    state = State(
        "light.test",
        STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.HS,
            ATTR_BRIGHTNESS: 122,
            ATTR_HS_COLOR: None,
        },
    )
    await strategy.calculate(state)
    assert "Could not calculate power" in caplog.text


async def test_sub_lut_loaded(hass: HomeAssistant) -> None:
    source_entity = create_source_entity(
        LIGHT_DOMAIN,
        [ColorMode.COLOR_TEMP, ColorMode.HS],
    )

    strategy = await _create_lut_strategy(
        hass,
        "yeelight",
        "YLDL01YL/ambilight",
        source_entity,
    )
    await strategy.validate_config()

    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(255, 588),
        expected_power=6.31,
    )


async def test_linked_profile_loaded(hass: HomeAssistant) -> None:
    source_entity = create_source_entity(
        LIGHT_DOMAIN,
        [ColorMode.COLOR_TEMP, ColorMode.HS],
    )
    strategy = await _create_lut_strategy(hass, "signify", "LCA007", source_entity)
    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(255, 588),
        expected_power=5.21,
    )


async def test_no_power_when_no_brightness_available(hass: HomeAssistant) -> None:
    """When brightness attribute is not available on state return no power"""
    strategy = await _create_lut_strategy(hass, "signify", "LCT010")

    state = State("light.test", STATE_ON, {ATTR_COLOR_MODE: ColorMode.BRIGHTNESS})
    assert not await strategy.calculate(state)


async def test_color_mode_unknown_is_handled_gracefully(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.at_level(logging.ERROR)
    strategy = await _create_lut_strategy(hass, "signify", "LCT010")

    state = State(
        "light.test",
        STATE_ON,
        {ATTR_COLOR_MODE: ColorMode.UNKNOWN, ATTR_BRIGHTNESS: 100},
    )
    assert not await strategy.calculate(state)
    assert "color mode unknown" in caplog.text


async def test_error_is_logged_when_color_temp_unavailable(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test error is logged when color_temp attribute is not available"""

    strategy = await _create_lut_strategy(hass, "signify", "LCT010")

    state = State(
        "light.test",
        STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_BRIGHTNESS: 100,
            ATTR_COLOR_TEMP_KELVIN: None,
        },
    )
    assert not await strategy.calculate(state)

    assert "Could not calculate power. no color temp set" in caplog.text


async def test_unsupported_color_mode(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.at_level(logging.ERROR)

    # This model only supports brightness
    strategy = await _create_lut_strategy(hass, "signify", "LWA017")

    state = _create_light_color_temp_state(100, 150)
    assert not await strategy.calculate(state)
    assert "Lookup table not found" in caplog.text


async def test_validation_fails_for_non_light_entities(hass: HomeAssistant) -> None:
    with pytest.raises(StrategyConfigurationError):
        strategy = await _create_lut_strategy(
            hass,
            "signify",
            "LCT010",
            source_entity=create_source_entity("sensor"),
        )
        await strategy.validate_config()


async def test_sensor_unavailable_for_unsupported_color_mode(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.at_level(logging.ERROR)
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LWA009",
        },
    )

    hass.states.async_set("light.test", STATE_ON, {ATTR_COLOR_MODE: ColorMode.BRIGHTNESS, ATTR_BRIGHTNESS: 100})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "3.48"

    hass.states.async_set("light.test", STATE_ON, {ATTR_COLOR_MODE: ColorMode.COLOR_TEMP, ATTR_BRIGHTNESS: 100})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE

    assert "Lookup table not found for color mode" in caplog.text


async def test_fallback_color_temp_to_hs(hass: HomeAssistant) -> None:
    """
    Test fallback is done when no color_temp.csv is available, but a hs.csv is.
    Fixes issue where HUE bridge is falsy reporting color_temp as color_mode.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2247
    """

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LLC011",
        },
    )

    hass.states.async_set(
        "light.test",
        STATE_ON,
        {ATTR_COLOR_MODE: ColorMode.COLOR_TEMP, ATTR_BRIGHTNESS: 100, ATTR_COLOR_TEMP_KELVIN: 500},
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "1.42"


async def test_warning_is_logged_when_color_mode_is_missing(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """
    Test that a warning is logged when the color_mode attribute is missing.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2323
    """
    caplog.set_level(logging.WARNING)
    strategy = await _create_lut_strategy(hass, "signify", "LCT010")

    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 100})
    assert not await strategy.calculate(state)
    assert "color mode unknown" in caplog.text


async def test_warning_is_logged_when_color_mode_is_none(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """
    Test that a warning is logged when the color_mode attribute is none.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2323
    """
    caplog.set_level(logging.WARNING)
    strategy = await _create_lut_strategy(hass, "signify", "LCT010")

    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 100, ATTR_COLOR_MODE: None})
    assert not await strategy.calculate(state)
    assert "color mode unknown" in caplog.text


async def test_fallback_to_non_gzipped_file(hass: HomeAssistant) -> None:
    """
    Test that a fallback is done when a gzipped file is not available.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2798
    """
    strategy = await _create_lut_strategy(
        hass,
        "test",
        "test",
        custom_profile_dir=get_test_profile_dir("lut_non_gzipped"),
    )
    await _calculate_and_assert_power(
        strategy,
        state=_create_light_color_temp_state(1, 153),
        expected_power=0.96,
    )


async def _create_lut_strategy(
    hass: HomeAssistant,
    manufacturer: str,
    model: str,
    source_entity: SourceEntity | None = None,
    custom_profile_dir: str | None = None,
) -> PowerCalculationStrategyInterface:
    if not source_entity:
        source_entity = create_source_entity(LIGHT_DOMAIN)
    strategy_factory = PowerCalculatorStrategyFactory(hass)
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo(manufacturer, model),
        custom_directory=custom_profile_dir,
    )
    return await strategy_factory.create(
        config={},
        strategy=CalculationStrategy.LUT,
        power_profile=power_profile,
        source_entity=source_entity,
    )


def _create_light_brightness_state(brightness: int) -> State:
    return State(
        "light.test",
        STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.BRIGHTNESS,
            ATTR_BRIGHTNESS: brightness,
        },
    )


def _create_light_color_temp_state(brightness: int, color_temp: int) -> State:
    return State(
        "light.test",
        STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_BRIGHTNESS: brightness,
            ATTR_COLOR_TEMP_KELVIN: color_util.color_temperature_mired_to_kelvin(color_temp),
        },
    )


def _create_light_hs_state(brightness: int, hue: int, sat: int) -> State:
    return State(
        "light.test",
        STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.HS,
            ATTR_BRIGHTNESS: brightness,
            ATTR_HS_COLOR: (hue, sat),
        },
    )


async def _calculate_and_assert_power(
    strategy: PowerCalculationStrategyInterface,
    state: State,
    expected_power: float | None,
) -> None:
    power = await strategy.calculate(state)
    if expected_power is None:
        assert power is None
        return

    assert round(power, 2) == round(Decimal(expected_power), 2)
