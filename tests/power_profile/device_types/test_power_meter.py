from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
)
from tests.common import get_test_profile_dir, run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_power_meter(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    sensor_id = "sensor.pm_mini"
    power_sensor_id = "sensor.pm_mini_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: sensor_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("power-meter"),
        },
    )

    hass.states.async_set(sensor_id, "50.00")
    await hass.async_block_till_done()

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "0.30"


async def test_power_meter_legacy(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    sensor_id = "sensor.pm_mini"
    power_sensor_id = "sensor.pm_mini_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: sensor_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("power-meter-legacy"),
        },
    )

    hass.states.async_set(sensor_id, "50.00")
    await hass.async_block_till_done()

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "0.30"
