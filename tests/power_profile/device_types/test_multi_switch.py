from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MULTI_SWITCH,
    DUMMY_ENTITY_ID,
)
from tests.common import assert_entity_state, get_test_profile_dir, run_powercalc_setup


async def test_multi_switch(hass: HomeAssistant) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    power_sensor_id = "sensor.outlet_device_power"
    switch1_id = "switch.outlet1"
    switch2_id = "switch.outlet2"

    hass.states.async_set(switch1_id, STATE_OFF)
    hass.states.async_set(switch2_id, STATE_OFF)
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Outlet",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("multi_switch2"),
            CONF_MULTI_SWITCH: {
                CONF_ENTITIES: [switch1_id, switch2_id],
            },
        },
    )

    assert_entity_state(hass, power_sensor_id, "0.25")

    await set_state_and_assert_power(hass, switch1_id, STATE_ON, "0.95")
    await set_state_and_assert_power(hass, switch2_id, STATE_ON, "1.65")
    await set_state_and_assert_power(hass, switch2_id, STATE_OFF, "0.95")
    await set_state_and_assert_power(hass, switch1_id, STATE_OFF, "0.25")


async def test_multi_switch_legacy(hass: HomeAssistant) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    switch1_id = "switch.outlet1"
    switch2_id = "switch.outlet2"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Outlet",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("multi_switch_legacy"),
            CONF_MULTI_SWITCH: {
                CONF_ENTITIES: [switch1_id, switch2_id],
            },
        },
    )

    hass.states.async_set(switch1_id, STATE_OFF)
    hass.states.async_set(switch2_id, STATE_OFF)
    await hass.async_block_till_done()
    await set_state_and_assert_power(hass, switch1_id, STATE_ON, "0.95")
    await set_state_and_assert_power(hass, switch2_id, STATE_ON, "1.40")
    await set_state_and_assert_power(hass, switch1_id, STATE_OFF, "0.95")
    await set_state_and_assert_power(hass, switch2_id, STATE_OFF, "0.50")


async def set_state_and_assert_power(hass: HomeAssistant, entity_id: str, state: str, expected_power: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()
    assert_entity_state(hass, "sensor.outlet_device_power", expected_power)
