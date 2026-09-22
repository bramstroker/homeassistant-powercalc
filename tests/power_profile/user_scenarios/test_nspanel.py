from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ColorMode
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_VARIABLES
from tests.common import assert_entity_state, get_test_profile_dir, run_powercalc_setup, set_states


async def test_relays_are_calculated_while_display_is_off(hass: HomeAssistant) -> None:
    """Relay power must remain active when the NSPanel display turns off."""
    display_entity = "light.nspanel_display"
    relay_1_entity = "switch.nspanel_relay_1"
    relay_2_entity = "switch.nspanel_relay_2"
    power_entity = "sensor.nspanel_display_power"

    await set_states(
        hass,
        [
            (
                display_entity,
                STATE_ON,
                {ATTR_BRIGHTNESS: 255, ATTR_COLOR_MODE: ColorMode.BRIGHTNESS},
            ),
            (relay_1_entity, STATE_OFF),
            (relay_2_entity, STATE_OFF),
        ],
    )
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: display_entity,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("nspanel"),
            CONF_VARIABLES: {
                "relay_1": relay_1_entity,
                "relay_2": relay_2_entity,
            },
        },
    )

    assert_entity_state(hass, power_entity, "1.88")

    await set_states(hass, [(relay_1_entity, STATE_ON)])
    assert_entity_state(hass, power_entity, "2.18")

    await set_states(hass, [(display_entity, STATE_OFF)])
    assert_entity_state(hass, power_entity, "1.46")

    await set_states(hass, [(relay_2_entity, STATE_ON)])
    assert_entity_state(hass, power_entity, "1.76")

    await set_states(hass, [(relay_1_entity, STATE_OFF)])
    assert_entity_state(hass, power_entity, "1.46")

    await set_states(
        hass,
        [
            (
                display_entity,
                STATE_ON,
                {ATTR_BRIGHTNESS: 255, ATTR_COLOR_MODE: ColorMode.BRIGHTNESS},
            ),
        ],
    )
    assert_entity_state(hass, power_entity, "2.18")
