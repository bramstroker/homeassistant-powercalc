from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CREATE_GROUP,
    CONF_GROUP_TYPE,
    CONF_SUBTRACT_ENTITIES,
    GroupType,
)
from tests.common import (
    run_powercalc_setup,
)


async def test_subtract(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.a_power", 100)
    hass.states.async_set("sensor.b_power", 20)
    hass.states.async_set("sensor.c_power", 25)

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test",
            CONF_GROUP_TYPE: GroupType.SUBTRACT,
            CONF_ENTITY_ID: "sensor.a_power",
            CONF_SUBTRACT_ENTITIES: [
                "sensor.b_power",
                "sensor.c_power",
            ],
        },
    )

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "55.00"

    hass.states.async_set("sensor.b_power", 22.45)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state.state == "52.55"
