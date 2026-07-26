from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_dyson_tp07(
    hass: HomeAssistant,
) -> None:
    """
    The profile uses nested `and` conditions with a scalar entity_id.

    See https://github.com/bramstroker/homeassistant-powercalc/pull/4378
    """
    fan_entity = "fan.test"
    power_entity = "sensor.test_power"
    await run_powercalc_setup(hass, {"entity_id": fan_entity, "manufacturer": "dyson", "model": "TP07"})

    assert hass.states.get(power_entity)

    await set_states(
        hass,
        [(fan_entity, STATE_ON, {ATTR_PERCENTAGE: 100, "oscillating": True, "direction": "reverse"})],
    )
    assert_entity_state(hass, power_entity, "28.48")

    await set_states(
        hass,
        [(fan_entity, STATE_ON, {ATTR_PERCENTAGE: 100, "oscillating": True, "direction": "forward"})],
    )
    assert_entity_state(hass, power_entity, "28.13")

    await set_states(
        hass,
        [(fan_entity, STATE_ON, {ATTR_PERCENTAGE: 100, "oscillating": False, "direction": "reverse"})],
    )
    assert_entity_state(hass, power_entity, "27.37")

    await set_states(
        hass,
        [(fan_entity, STATE_ON, {ATTR_PERCENTAGE: 100, "oscillating": False, "direction": "forward"})],
    )
    assert_entity_state(hass, power_entity, "27.36")
