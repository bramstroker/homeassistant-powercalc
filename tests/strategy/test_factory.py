from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CONF_COMPOSITE, CONF_STRATEGIES, CalculationStrategy
from custom_components.powercalc.errors import (
    StrategyConfigurationError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory


async def test_exception_raised_on_not_supported_strategy(hass: HomeAssistant) -> None:
    factory = PowerCalculatorStrategyFactory(hass)
    source_entity = create_source_entity("light.test", hass)

    with pytest.raises(UnsupportedStrategyError):
        await factory.create(
            {},
            "NonExistingStrategy",
            power_profile=None,
            source_entity=source_entity,
        )


async def test_exception_raised_when_no_power_profile_passed_lut_strategy(
    hass: HomeAssistant,
) -> None:
    factory = PowerCalculatorStrategyFactory(hass)
    source_entity = create_source_entity("light.test", hass)

    with pytest.raises(StrategyConfigurationError):
        await factory.create(
            {},
            CalculationStrategy.LUT,
            power_profile=None,
            source_entity=source_entity,
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
    factory = PowerCalculatorStrategyFactory(hass)
    source_entity = create_source_entity("light.test", hass)

    with pytest.raises(StrategyConfigurationError):
        await factory.create(
            {},
            strategy,
            power_profile=None,
            source_entity=source_entity,
        )


async def test_exception_raised_when_composite_has_no_strategies(hass: HomeAssistant) -> None:
    factory = PowerCalculatorStrategyFactory(hass)
    source_entity = create_source_entity("light.test", hass)

    with pytest.raises(StrategyConfigurationError):
        await factory.create(
            {CONF_COMPOSITE: {CONF_STRATEGIES: []}},
            CalculationStrategy.COMPOSITE,
            power_profile=None,
            source_entity=source_entity,
        )
