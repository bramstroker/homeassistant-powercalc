from homeassistant.core import HomeAssistant

from tests.common import run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_reolink_e1_pro(hass: HomeAssistant, mock_entity_with_model_information: MockEntityWithModel) -> None:
    camera_id = "camera.test_camera"

    power_sensor_id = "sensor.test_camera_power"
    day_night_state_id = "sensor.test_camera_day_night_state"

    hass.states.async_set(camera_id, "recording")
    hass.states.async_set(day_night_state_id, "day")
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            "entity_id": camera_id,
            "manufacturer": "test",
            "model": "reolink_camera",
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "2.51"

    # Switch to night mode
    hass.states.async_set(
        day_night_state_id,
        "night",
    )

    await hass.async_block_till_done()
    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "4.08"
