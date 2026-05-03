from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_wiz_nightlight(
    hass: HomeAssistant,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/3992
    """
    light_entity = "light.test"
    power_entity = "sensor.test_power"
    await run_powercalc_setup(hass, {"entity_id": light_entity, "manufacturer": "wiz", "model": "SHRGBC"})

    assert hass.states.get(power_entity)

    await set_states(hass, [(light_entity, STATE_ON, {"effect": "Night light"})])
    assert_entity_state(hass, power_entity, "1.24")

    await set_states(hass, [(light_entity, STATE_ON, {"brightness": 128, "color_mode": "hs", "hs_color": [0, 0]})])
    assert_entity_state(hass, power_entity, "3.96")
