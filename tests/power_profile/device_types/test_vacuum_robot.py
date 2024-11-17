from homeassistant.components.vacuum import STATE_CLEANING, STATE_DOCKED
from homeassistant.const import ATTR_BATTERY_LEVEL, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
)
from tests.common import get_test_profile_dir, run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_vacuum_robot(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    vacuum_id = "vacuum.roomba"

    power_sensor_id = "sensor.roomba_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: vacuum_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("vacuum_robot"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(vacuum_id, STATE_CLEANING, {ATTR_BATTERY_LEVEL: 50})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.00"

    hass.states.async_set(vacuum_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 0})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "20.00"

    hass.states.async_set(vacuum_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 85})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "15.00"

    hass.states.async_set(vacuum_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 100})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.50"
