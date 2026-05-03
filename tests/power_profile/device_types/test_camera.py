from homeassistant.core import HomeAssistant

from tests.common import assert_entity_state, run_powercalc_setup, set_states
from tests.conftest import MockEntityWithModel


async def test_reolink_e1_pro(hass: HomeAssistant, mock_entity_with_model_information: MockEntityWithModel) -> None:
    camera_id = "camera.test_camera"

    power_sensor_id = "sensor.test_camera_power"
    day_night_state_id = "sensor.test_camera_day_night_state"

    await set_states(hass, [(camera_id, "recording"), (day_night_state_id, "day")])
    await run_powercalc_setup(
        hass,
        {
            "entity_id": camera_id,
            "manufacturer": "test",
            "model": "reolink_camera",
        },
    )

    assert_entity_state(hass, power_sensor_id, "2.51")

    # Switch to night mode
    await set_states(
        hass,
        [
            (
                day_night_state_id,
                "night",
            ),
        ],
    )
    assert_entity_state(hass, power_sensor_id, "4.08")
