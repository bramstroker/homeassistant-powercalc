from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_STANDBY_POWER_ON,
)
from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_reolink_e1_pro(hass: HomeAssistant) -> None:
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


async def test_reolink_keeps_configured_standby_power_on_on_sub_profile_switch(
    hass: HomeAssistant,
) -> None:
    """A configured standby_power_on must survive the automatic day to night sub profile switch.

    The sub profile switch reloads the standby power from the power profile. When the value was
    configured on the sensor instead, it has to win over the profile, just like during setup.
    """
    camera_id = "camera.test_camera"

    power_sensor_id = "sensor.test_camera_power"
    day_night_state_id = "sensor.test_camera_day_night_state"

    await set_states(hass, [(camera_id, "recording"), (day_night_state_id, "day")])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: camera_id,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "reolink_camera",
            CONF_STANDBY_POWER_ON: 0.5,
        },
    )

    # 2.51 W day profile + 0.5 W standby_power_on
    assert_entity_state(hass, power_sensor_id, "3.01")

    await set_states(hass, [(day_night_state_id, "night")])

    # 4.08 W night profile + 0.5 W standby_power_on, the configured value must not be dropped
    assert_entity_state(hass, power_sensor_id, "4.58")
