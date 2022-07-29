import logging
from decimal import Decimal
from typing import Optional

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ColorMode,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CalculationStrategy
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.power_profile.light_model import LightModel
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from custom_components.powercalc.strategy.lut import LutStrategy

from .common import create_source_entity


async def test_colortemp_lut(hass: HomeAssistant):
    """Test LUT lookup in color_temp mode"""

    source_entity = create_source_entity("light", [ColorMode.COLOR_TEMP])

    strategy = _create_lut_strategy(hass, "signify", "LCT010", source_entity)
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


async def test_brightness_lut(hass: HomeAssistant):
    """Test LUT lookup in brightness mode"""

    source_entity = create_source_entity("light", [ColorMode.BRIGHTNESS])

    strategy = _create_lut_strategy(hass, "signify", "LWB010", source_entity)
    await strategy.validate_config()

    await _calculate_and_assert_power(
        strategy, state=_create_light_brightness_state(100), expected_power=2.05
    )

    # Out of bounds brightness. Power for bri 255 should be returned and no error
    await _calculate_and_assert_power(
        strategy, state=_create_light_brightness_state(450), expected_power=9.65
    )


async def test_sub_lut_loaded(hass: HomeAssistant):
    source_entity = create_source_entity("light", [ColorMode.COLOR_TEMP, ColorMode.HS])

    strategy = _create_lut_strategy(
        hass, "yeelight", "YLDL01YL/ambilight", source_entity
    )
    await strategy.validate_config()

    await _calculate_and_assert_power(
        strategy, state=_create_light_color_temp_state(255, 588), expected_power=6.31
    )

async def test_linked_profile_loaded(hass: HomeAssistant):
    source_entity = create_source_entity("light", [ColorMode.COLOR_TEMP, ColorMode.HS])
    strategy = _create_lut_strategy(
        hass, "signify", "LCA007", source_entity
    )
    await _calculate_and_assert_power(
        strategy, state=_create_light_color_temp_state(255, 588), expected_power=5.21
    )

async def test_no_power_when_no_brightness_available(hass: HomeAssistant):
    """When brightness attribute is not available on state return no power"""
    strategy = _create_lut_strategy(hass, "signify", "LCT010")

    state = State("light.test", STATE_ON, {ATTR_COLOR_MODE: ColorMode.BRIGHTNESS})
    assert not await strategy.calculate(state)


async def test_color_mode_unknown_is_handled_gracefully(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.at_level(logging.ERROR)
    strategy = _create_lut_strategy(hass, "signify", "LCT010")

    state = State(
        "light.test",
        STATE_ON,
        {ATTR_COLOR_MODE: ColorMode.UNKNOWN, ATTR_BRIGHTNESS: 100},
    )
    assert not await strategy.calculate(state)
    assert "color mode unknown" in caplog.text


async def test_validation_fails_for_non_light_entities(hass: HomeAssistant):
    with pytest.raises(StrategyConfigurationError):
        strategy = _create_lut_strategy(
            hass, "signify", "LCT010", source_entity=create_source_entity("sensor")
        )
        await strategy.validate_config()


def _create_lut_strategy(
    hass: HomeAssistant,
    manufacturer: str,
    model: str,
    source_entity: Optional[SourceEntity] = None,
) -> LutStrategy:
    if not source_entity:
        source_entity = create_source_entity("light")
    strategy_factory = PowerCalculatorStrategyFactory(hass)
    return strategy_factory.create(
        config={},
        strategy=CalculationStrategy.LUT,
        light_model=LightModel(hass, manufacturer, model, None),
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
            ATTR_COLOR_TEMP: color_temp,
        },
    )


async def _calculate_and_assert_power(
    strategy: LutStrategy, state: State, expected_power: float
):
    power = await strategy.calculate(state)
    assert round(Decimal(expected_power), 2) == round(power, 2)
