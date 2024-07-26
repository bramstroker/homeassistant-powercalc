from decimal import Decimal

import pytest
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc import PowerCalculatorStrategyFactory
from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CONF_MULTI_SWITCH, CONF_POWER, CONF_POWER_OFF, CalculationStrategy
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.multi_switch import MultiSwitchStrategy
from tests.common import run_powercalc_setup


async def test_calculate_sum(hass: HomeAssistant) -> None:
    switch1 = "switch.test1"
    switch2 = "switch.test2"
    switch3 = "switch.test3"

    strategy = MultiSwitchStrategy(
        hass,
        [switch1, switch2, switch3],
        on_power=Decimal(0.5),
        off_power=Decimal(0.25),
    )

    assert await strategy.calculate(State(switch1, STATE_OFF)) == 0.75
    assert await strategy.calculate(State(switch1, STATE_ON)) == 1.00
    assert await strategy.calculate(State(switch2, STATE_ON)) == 1.25
    assert await strategy.calculate(State(switch3, STATE_ON)) == 1.50


async def test_setup_using_yaml(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Outlet self usage",
            CONF_MULTI_SWITCH: {
                CONF_POWER: 0.5,
                CONF_POWER_OFF: 0.25,
                CONF_ENTITIES: [
                    "switch.test1",
                    "switch.test2",
                    "switch.test3",
                ],
            },
        },
    )
    await hass.async_block_till_done()

    hass.states.async_set("switch.test1", STATE_ON)
    await hass.async_block_till_done()

    power_sensor = hass.states.get("sensor.outlet_self_usage_power")
    assert power_sensor


@pytest.mark.parametrize(
    "config",
    [
        {
            CONF_NAME: "Outlet self usage",
            CONF_MULTI_SWITCH: {
                CONF_POWER: 0.5,
                CONF_POWER_OFF: 1,
            },
        },
        {
            CONF_NAME: "Outlet self usage",
            CONF_MULTI_SWITCH: {
                CONF_POWER: 0.5,
                CONF_ENTITIES: [
                    "switch.test1",
                    "switch.test2",
                    "switch.test3",
                ],
            },
        },
        {
            CONF_NAME: "Outlet self usage",
            CONF_MULTI_SWITCH: {
                CONF_POWER_OFF: 0.5,
                CONF_ENTITIES: [
                    "switch.test1",
                    "switch.test2",
                    "switch.test3",
                ],
            },
        },
    ],
)
async def test_strategy_configuration_error(hass: HomeAssistant, config: ConfigType) -> None:
    with pytest.raises(StrategyConfigurationError):
        factory = PowerCalculatorStrategyFactory(hass)
        await factory.create(
            {
                CONF_NAME: "Outlet self usage",
                CONF_MULTI_SWITCH: {
                    CONF_POWER: 0.5,
                    CONF_ENTITIES: [
                        "switch.test1",
                        "switch.test2",
                        "switch.test3",
                    ],
                },
            },
            CalculationStrategy.MULTI_SWITCH,
            None,
            await create_source_entity("switch.test1", hass),
        )
