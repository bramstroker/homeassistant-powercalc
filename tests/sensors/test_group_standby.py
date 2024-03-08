from homeassistant.const import (
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    EVENT_HOMEASSISTANT_STARTED,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_STANDBY_POWER,
    CalculationStrategy,
)
from tests.common import create_input_booleans, run_powercalc_setup


async def test_standby_group(hass: HomeAssistant) -> None:
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test1",
                    CONF_STANDBY_POWER: 0.2,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 20},
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test2",
                    CONF_STANDBY_POWER: 0.3,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 40},
                },
            ],
        },
    )
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    hass.states.async_set("input_boolean.test1", STATE_ON)
    hass.states.async_set("input_boolean.test2", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.all_standby_power")
    assert power_state
    assert power_state.state == STATE_UNKNOWN

    energy_state = hass.states.get("sensor.all_standby_energy")
    assert energy_state

    hass.states.async_set("input_boolean.test1", STATE_OFF)
    hass.states.async_set("input_boolean.test2", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_standby_power").state == "0.50"

    hass.states.async_set("input_boolean.test2", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_standby_power").state == "0.20"
