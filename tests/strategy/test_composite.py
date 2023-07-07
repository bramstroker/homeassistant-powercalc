
from homeassistant.const import (
    CONF_ENTITY_ID,
    STATE_ON,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER,
)
from tests.common import (
    run_powercalc_setup,
)


async def test_composite(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "light.test",
        "composite": {
            "strategies": [
                {
                    "condition": "test",
                    CONF_FIXED: {
                        CONF_POWER: 50,
                    },
                },
                {
                    "condition": "test",
                    CONF_LINEAR: {
                        CONF_MIN_POWER: 10,
                        CONF_MAX_POWER: 20,
                    },
                },
            ],
        },
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "50.00"
