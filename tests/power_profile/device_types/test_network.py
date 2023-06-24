from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

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

    mock_entity_with_model_information(
        entity_id=binary_sensor_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.wifi_repeater_device_power"

    await run_powercalc_setup(hass, {})

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(binary_sensor_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "3.00"

    hass.states.async_set(binary_sensor_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.00"
