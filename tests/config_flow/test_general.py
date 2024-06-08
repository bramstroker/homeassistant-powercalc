from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_MODE,
    CONF_POWER,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
)
from tests.config_flow.common import (
    goto_virtual_power_strategy_step,
    set_virtual_power_configuration,
)


async def test_create_multiple_entries_using_dummy(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1974"""
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "mysensor1",
            CONF_MODE: CalculationStrategy.FIXED,
        },
    )
    await set_virtual_power_configuration(hass, result, {CONF_POWER: 20})

    await hass.async_block_till_done()
    assert hass.states.get("sensor.mysensor1_power")
    assert hass.states.get("sensor.mysensor1_energy")

    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "mysensor2",
            CONF_MODE: CalculationStrategy.FIXED,
        },
    )
    await set_virtual_power_configuration(hass, result, {CONF_POWER: 20})

    await hass.async_block_till_done()
    assert hass.states.get("sensor.mysensor2_power")
    assert hass.states.get("sensor.mysensor2_energy")
