from homeassistant.setup import async_setup_component
from homeassistant.core import State
from homeassistant.const import (
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ATTR_HS_COLOR, ATTR_COLOR_TEMP,
    ColorMode
)
from homeassistant.helpers.template import Template
from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CalculationStrategy
from custom_components.powercalc.power_profile.light_model import LightModel
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory

from custom_components.powercalc.strategy.lut import LutStrategy
from .common import create_source_entity
from decimal import Decimal

async def test_colortemp_lut(hass: HomeAssistant):
    source_entity = create_source_entity("light")

    strategy_factory = PowerCalculatorStrategyFactory(hass)
    strategy = strategy_factory.create(
        config={},
        strategy=CalculationStrategy.LUT,
        light_model=LightModel(hass, "signify", "LCT010", None),
        source_entity=source_entity
    )
    state = State(
        source_entity.entity_id, STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_BRIGHTNESS: 100,
            ATTR_COLOR_TEMP: 300
        }
    )
    assert 2.5 == await strategy.calculate(state)

    state = State(
        source_entity.entity_id, STATE_ON,
        {
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_BRIGHTNESS: 144,
            ATTR_COLOR_TEMP: 450
        }
    )
    val = round(await strategy.calculate(state), 2)
    assert round(Decimal(3.01), 2) == val

