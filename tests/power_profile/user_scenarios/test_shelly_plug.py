from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant

from tests.common import assert_entity_state, mock_device_with_entities, run_powercalc_setup, set_states


async def test_shelly_plug_auto_sub_profile(
    hass: HomeAssistant,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/3370#issuecomment-3102005428
    """
    mock_device_with_entities(
        hass,
        "switch.test",
        "shelly",
        "Shelly Plug S",
        platform="shelly",
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
        },
    )

    await set_states(hass, [("switch.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_device_power", "0.80")
