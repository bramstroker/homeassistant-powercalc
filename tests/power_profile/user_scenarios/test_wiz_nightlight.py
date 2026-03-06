from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from tests.common import run_powercalc_setup


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

    hass.states.async_set(light_entity, STATE_ON, {"effect": "Night light"})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity).state == "1.24"

    hass.states.async_set(light_entity, STATE_ON, {"brightness": 128, "color_mode": "hs", "hs_color": [0, 0]})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity).state == "3.96"
