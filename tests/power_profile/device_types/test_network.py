from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL
from tests.common import run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_network_device(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that smart plug can be setup from profile library
    """
    binary_sensor_id = "binary_sensor.wifi_repeater"
    manufacturer = "AVM"
    model = "FRITZ!Repeater 1200 AX"

    power_sensor_id = "sensor.wifi_repeater_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: binary_sensor_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(binary_sensor_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "3.00"

    hass.states.async_set(binary_sensor_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.00"
