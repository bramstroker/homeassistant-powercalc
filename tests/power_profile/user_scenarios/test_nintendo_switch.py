from datetime import timedelta

from homeassistant.const import CONF_ENTITY_ID, STATE_HOME, STATE_NOT_HOME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.powercalc.const import (
    CONF_DELAY,
    CONF_FIXED,
    CONF_POWER,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
)
from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_nintendo_switch(hass: HomeAssistant) -> None:
    """
    See https://community.home-assistant.io/t/powercalc-virtual-power-sensors/318515/840?u=bramski
    """
    device_tracker_id = "device_tracker.boo"
    media_player_device_id = "media_player.baa"
    power_sensor_id = "sensor.boo_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: device_tracker_id,
            CONF_FIXED: {
                CONF_POWER: "{{ iif(state_attr('media_player.baa', 'source') == 'Game', 8.0, 0) }}",  # codespell:ignore iif
            },
            CONF_SLEEP_POWER: {
                CONF_POWER: 0,
                CONF_DELAY: 2700,
            },
            CONF_STANDBY_POWER: 12,
        },
    )

    await set_states(hass, [(media_player_device_id, STATE_ON, {"source": "Game"})])
    assert_entity_state(hass, power_sensor_id, "unavailable")

    await set_states(hass, [(device_tracker_id, STATE_HOME)])
    assert_entity_state(hass, power_sensor_id, "8.00")

    await set_states(hass, [(media_player_device_id, STATE_ON, {"source": "TV"})])
    assert_entity_state(hass, power_sensor_id, "0.00")

    await set_states(hass, [(device_tracker_id, STATE_NOT_HOME)])
    assert_entity_state(hass, power_sensor_id, "12.00")

    # After 10 seconds the device goes into sleep mode, check the sleep power is set on the power sensor
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=3000))

    assert_entity_state(hass, power_sensor_id, "0.00")
