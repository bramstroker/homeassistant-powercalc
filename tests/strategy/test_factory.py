import pytest
from homeassistant.core import HomeAssistant
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from custom_components.powercalc.const import CalculationStrategy
from custom_components.powercalc.errors import UnsupportedMode, StrategyConfigurationError
from .common import create_source_entity


async def test_exception_raised_on_not_supported_strategy(hass: HomeAssistant) -> None:
    with pytest.raises(UnsupportedMode):
        factory = PowerCalculatorStrategyFactory(hass)
        factory.create({}, "NonExistingStrategy", power_profile=None, source_entity=create_source_entity("light"))


async def test_exception_raised_when_no_power_profile_passed_lut_strategy(hass: HomeAssistant) -> None:
    with pytest.raises(StrategyConfigurationError):
        factory = PowerCalculatorStrategyFactory(hass)
        factory.create({}, CalculationStrategy.LUT, power_profile=None, source_entity=create_source_entity("light"))

