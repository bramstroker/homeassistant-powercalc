from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import (
    CONF_CONDITION,
    CONF_ENTITY_ID,
    STATE_ON,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER,
    CONF_STRATEGIES,
)
from tests.common import (
    run_powercalc_setup,
)


async def test_composite(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "light.test",
        CONF_COMPOSITE: {
            CONF_STRATEGIES: [
                {
                    CONF_CONDITION:
                        {
                            "condition": "numeric_state",
                            "entity_id": "sensor.temperature",
                            "above": 17,
                            "below": 25,
                        }
                    ,
                    CONF_FIXED: {
                        CONF_POWER: 50,
                    },
                },
                {
                    CONF_CONDITION:
                        {
                            "condition": "state",
                            "entity_id": "light.test",
                            "state": "on",
                        }
                    ,
                    CONF_LINEAR: {
                        CONF_MIN_POWER: 10,
                        CONF_MAX_POWER: 20,
                    },
                },
            ],
        },
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("sensor.temperature", "12")
    await hass.async_block_till_done()
    hass.states.async_set("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "17.84"
