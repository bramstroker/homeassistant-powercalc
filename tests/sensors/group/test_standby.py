from homeassistant.const import (
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_CREATE_STANDBY_GROUP
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_STANDBY_POWER,
    CalculationStrategy,
)
from tests.common import run_powercalc_setup


async def test_standby_group(hass: HomeAssistant) -> None:
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


async def test_self_usage_sensors_included(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "switch.test1",
                    CONF_STANDBY_POWER: 0.2,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 20},
                },
                {
                    CONF_ENTITY_ID: "switch.test2",
                    CONF_MANUFACTURER: "test",
                    CONF_MODEL: "smart_switch_with_pm_new",
                },
            ],
        },
    )

    hass.states.async_set("switch.test1", STATE_ON)
    hass.states.async_set("switch.test2", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_standby_power").state == "0.70"

    hass.states.async_set("switch.test1", STATE_OFF)
    hass.states.async_set("switch.test2", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_standby_power").state == "0.50"

    hass.states.async_set("switch.test1", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_standby_power").state == "0.30"


async def test_disable_group_creation(hass: HomeAssistant) -> None:
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
            ],
        },
        {
            CONF_CREATE_STANDBY_GROUP: False,
        },
    )

    hass.states.async_set("input_boolean.test1", STATE_OFF)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.all_standby_power")
    assert not power_state
