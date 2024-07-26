from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MULTI_SWITCH,
    CONF_POWER,
    CONF_STANDBY_POWER,
)
from tests.common import get_test_profile_dir, run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_multi_switch(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    switch_id = "switch.outlet1"
    manufacturer = "Tp-Link"
    model = "HS300"

    mock_entity_with_model_information(
        entity_id=switch_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.outlet1_device_power"
    switch1_id = "switch.outlet1"
    switch2_id = "switch.outlet2"
    switch3_id = "switch.outlet3"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: switch_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("multi_switch"),
            CONF_STANDBY_POWER: 0.25,
            CONF_MULTI_SWITCH: {
                CONF_POWER: 0.687,
                CONF_ENTITIES: [
                    switch1_id,
                    switch2_id,
                    switch3_id,
                ],
            },
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(switch1_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.19"

    hass.states.async_set(switch2_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.62"

    hass.states.async_set(switch2_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.19"
