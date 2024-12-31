from datetime import timedelta

from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import (
    CONF_CONDITION,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import async_fire_time_changed, mock_device_registry, mock_registry

from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MULTI_SWITCH,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_STANDBY_POWER,
    CONF_STRATEGIES,
)
from custom_components.powercalc.strategy.composite import CompositeMode
from tests.common import (
    get_test_config_dir,
    get_test_profile_dir,
    run_powercalc_setup,
)


async def test_composite(hass: HomeAssistant) -> None:
    mock_device_registry(
        hass,
        {
            "my-device-id": DeviceEntry(
                id="my-device-id",
                manufacturer="foo",
                model="bar",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="my-device-id",
            ),
        },
    )

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

    # set states to unavailable, so entities are there when setting up powercalc
    hass.states.async_set("light.test", STATE_UNAVAILABLE)
    hass.states.async_set("binary_sensor.test1", STATE_UNAVAILABLE)
    hass.states.async_set("binary_sensor.test2", STATE_UNAVAILABLE)
    hass.states.async_set("binary_sensor.test3", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

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


async def test_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()

    dishwasher_mode_entity = "sensor.dishwasher_operating_mode"

    hass.states.async_set(dishwasher_mode_entity, "Cycle Complete")
    await hass.async_block_till_done()

    sensor_config = {
        CONF_ENTITY_ID: dishwasher_mode_entity,
        CONF_NAME: "Dishwasher",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "entity_id": dishwasher_mode_entity,
                    "state": "Cycle Active",
                },
                CONF_PLAYBOOK: {
                    CONF_PLAYBOOKS: {
                        "playbook": "composite/dishwasher.csv",
                    },
                },
            },
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "entity_id": dishwasher_mode_entity,
                    "state": "Cycle Complete",
                },
                CONF_FIXED: {
                    CONF_POWER: 9.6,
                },
            },
            {
                CONF_FIXED: {
                    CONF_POWER: 1.6,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set(dishwasher_mode_entity, "Cycle Complete")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_power").state == "9.60"

    hass.states.async_set(dishwasher_mode_entity, "Cycle Paused")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_power").state == "1.60"

    hass.states.async_set(dishwasher_mode_entity, "Cycle Active")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_power").state == "20.00"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_power").state == "40.00"

    hass.states.async_set(dishwasher_mode_entity, "Cycle Complete")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_power").state == "9.60"

    hass.states.async_set(dishwasher_mode_entity, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_power").state == "0.00"


async def test_calculate_standby_power(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "switch.test",
        CONF_STANDBY_POWER: 1,
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "entity_id": "switch.test",
                    "state": STATE_OFF,
                },
                CONF_MULTI_SWITCH: {
                    CONF_POWER: 5,
                    CONF_POWER_OFF: 2,
                    CONF_ENTITIES: [
                        "switch.test1",
                        "switch.test2",
                    ],
                },
            },
            {
                CONF_FIXED: {
                    CONF_POWER: 10,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("switch.test1", STATE_OFF)
    hass.states.async_set("switch.test2", STATE_OFF)
    hass.states.async_set("switch.test", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "4.00"

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "10.00"


async def test_calculate_standby_power2(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENTITY_ID: "switch.test",
        CONF_STANDBY_POWER: 1,
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "entity_id": "switch.test",
                    "state": STATE_OFF,
                },
                CONF_FIXED: {
                    CONF_POWER: 5,
                },
            },
            {
                CONF_MULTI_SWITCH: {
                    CONF_POWER: 5,
                    CONF_POWER_OFF: 2,
                    CONF_ENTITIES: [
                        "switch.test1",
                        "switch.test2",
                    ],
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("switch.test", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "1.00"


async def test_composite_strategy_from_library_profile(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("composite"),
        },
    )

    hass.states.async_set("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.82"


async def test_composite_mode_sum(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.test", 50)

    sensor_config = {
        CONF_ENTITY_ID: "light.test",
        CONF_COMPOSITE: {
            CONF_MODE: CompositeMode.SUM_ALL,
            CONF_STRATEGIES: [
                {
                    CONF_FIXED: {
                        CONF_POWER: 10,
                    },
                },
                {
                    CONF_FIXED: {
                        CONF_POWER: 20,
                    },
                },
                {
                    CONF_CONDITION: {
                        "condition": "numeric_state",
                        "entity_id": "sensor.test",
                        "above": 100,
                    },
                    CONF_FIXED: {
                        CONF_POWER: 30,
                    },
                },
            ],
        },
    }

    await run_powercalc_setup(hass, sensor_config, {})

    hass.states.async_set("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "30.00"


async def test_sum_mode_from_library_profile(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "sensor.test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("composite_sum"),
        },
    )

    hass.states.async_set("sensor.test", "100")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "22.00"

    hass.states.async_set("sensor.test", "20")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "2.00"


async def test_numeric_state_omit_entity_id(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.test", 2000)

    sensor_config = {
        CONF_ENTITY_ID: "sensor.test",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "numeric_state",
                    "above": 100,
                },
                CONF_FIXED: {
                    CONF_POWER: 1000,
                },
            },
            {
                CONF_FIXED: {
                    CONF_POWER: 500,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    assert hass.states.get("sensor.test_power").state == "1000.00"

    hass.states.async_set("sensor.test", 100)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "500.00"


async def test_state_omit_entity_id(hass: HomeAssistant) -> None:
    hass.states.async_set("media_player.test", STATE_PAUSED)

    sensor_config = {
        CONF_ENTITY_ID: "media_player.test",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "state": STATE_PLAYING,
                },
                CONF_FIXED: {
                    CONF_POWER: 1000,
                },
            },
            {
                CONF_FIXED: {
                    CONF_POWER: 500,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    assert hass.states.get("sensor.test_power").state == "500.00"

    hass.states.async_set("media_player.test", STATE_PLAYING)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "1000.00"


async def test_state_attribute_entity_id(hass: HomeAssistant) -> None:
    hass.states.async_set("media_player.test", STATE_PLAYING, {"source": "HDMI2"})

    sensor_config = {
        CONF_ENTITY_ID: "media_player.test",
        CONF_COMPOSITE: [
            {
                CONF_CONDITION: {
                    "condition": "state",
                    "attribute": "source",
                    "state": "HDMI1",
                },
                CONF_FIXED: {
                    CONF_POWER: 20,
                },
            },
            {
                CONF_FIXED: {
                    CONF_POWER: 2,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    assert hass.states.get("sensor.test_power").state == "2.00"

    hass.states.async_set("media_player.test", STATE_PLAYING, {"source": "HDMI1"})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.00"
