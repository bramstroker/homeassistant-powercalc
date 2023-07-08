from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import (
    CONF_CONDITION,
    CONF_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_COMPOSITE,
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
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "numeric_state",
                    "entity_id": "sensor.temperature",
                    "above": 17,
                    "below": 25,
                },
                CONF_FIXED: {
                    CONF_POWER: 50,
                },
            },
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "entity_id": "light.test",
                    "state": "on",
                },
                CONF_LINEAR: {
                    CONF_MIN_POWER: 10,
                    CONF_MAX_POWER: 20,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("sensor.temperature", "12")
    await hass.async_block_till_done()
    hass.states.async_set("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "17.84"


async def test_template_condition(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "light.test",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "template",
                    "value_template": "{{ (state_attr('device_tracker.iphone', 'battery_level')|int) > 50 }}",
                },
                CONF_FIXED: {
                    CONF_POWER: 10,
                },
            },
            {
                CONF_FIXED: {
                    CONF_POWER: 20,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("device_tracker.iphone", STATE_ON, {"battery_level": "60"})
    await hass.async_block_till_done()

    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "10.00"

    hass.states.async_set("device_tracker.iphone", STATE_ON, {"battery_level": "40"})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.00"


async def test_power_sensor_unavailable_when_no_condition_matches(
    hass: HomeAssistant,
) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "light.test",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "entity_id": "light.test",
                    "state": STATE_OFF,
                },
                CONF_FIXED: {
                    CONF_POWER: 10,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE


async def test_nested_conditions(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "light.test",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "and",
                    "conditions": [
                        {
                            "condition": "state",
                            "entity_id": "binary_sensor.test1",
                            "state": STATE_OFF,
                        },
                        {
                            "condition": "or",
                            "conditions": [
                                {
                                    "condition": "state",
                                    "entity_id": "binary_sensor.test2",
                                    "state": STATE_ON,
                                },
                                {
                                    "condition": "template",
                                    "value_template": "{{ is_state('binary_sensor.test3', 'on')  }}",
                                },
                            ],
                        },
                    ],
                },
                CONF_FIXED: {
                    CONF_POWER: 10,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("light.test", STATE_ON)

    hass.states.async_set("binary_sensor.test1", STATE_OFF)
    hass.states.async_set("binary_sensor.test2", STATE_ON)
    hass.states.async_set("binary_sensor.test3", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "10.00"

    hass.states.async_set("binary_sensor.test1", STATE_OFF)
    hass.states.async_set("binary_sensor.test2", STATE_OFF)
    hass.states.async_set("binary_sensor.test3", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "10.00"

    hass.states.async_set("binary_sensor.test1", STATE_ON)
    hass.states.async_set("binary_sensor.test2", STATE_OFF)
    hass.states.async_set("binary_sensor.test3", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE
