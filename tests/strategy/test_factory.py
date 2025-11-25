from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CalculationStrategy
from custom_components.powercalc.errors import (
    StrategyConfigurationError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory


async def test_exception_raised_on_not_supported_strategy(hass: HomeAssistant) -> None:
    with pytest.raises(UnsupportedStrategyError):
        factory = PowerCalculatorStrategyFactory(hass)
        await factory.create(
            {},
            "NonExistingStrategy",
            power_profile=None,
            source_entity=await create_source_entity("light.test", hass),
        )


async def test_exception_raised_when_no_power_profile_passed_lut_strategy(
    hass: HomeAssistant,
) -> None:
    with pytest.raises(StrategyConfigurationError):
        factory = PowerCalculatorStrategyFactory(hass)
        await factory.create(
            {},
            CalculationStrategy.LUT,
            power_profile=None,
            source_entity=await create_source_entity("light.test", hass),
        )


@pytest.mark.parametrize(
    "strategy",
    [
        CalculationStrategy.FIXED,
        CalculationStrategy.LINEAR,
        CalculationStrategy.WLED,
        CalculationStrategy.PLAYBOOK,
        CalculationStrategy.COMPOSITE,
    ],
)
async def test_exception_raised_when_strategy_config_not_provided(
    hass: HomeAssistant,
    strategy: CalculationStrategy,
) -> None:
    with pytest.raises(StrategyConfigurationError):
        factory = PowerCalculatorStrategyFactory(hass)
        await factory.create(
            {},
            strategy,
            power_profile=None,
            source_entity=await create_source_entity("light.test", hass),
        )
