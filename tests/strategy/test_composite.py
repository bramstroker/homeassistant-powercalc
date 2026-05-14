from datetime import timedelta

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ATTR_EFFECT, ColorMode
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
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults, async_fire_time_changed, mock_registry

from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
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
    assert_entity_state,
    get_test_profile_dir,
    mock_device,
    run_powercalc_setup,
    set_states,
)


async def test_composite(hass: HomeAssistant) -> None:
    mock_device(hass, "my-device-id", "foo", "bar")

    mock_registry(
        hass,
        {
            "light.test": RegistryEntryWithDefaults(
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
                    "state": STATE_ON,
                },
                CONF_LINEAR: {
                    CONF_MIN_POWER: 10,
                    CONF_MAX_POWER: 20,
                },
            },
        ],
    }

    await run_powercalc_setup(hass, sensor_config, {})

    await set_states(hass, [("sensor.temperature", "12"), ("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})])
    assert_entity_state(hass, "sensor.test_power", "17.84")


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

    await set_states(hass, [("device_tracker.iphone", STATE_ON, {"battery_level": "60"}), ("light.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "10.00")

    await set_states(hass, [("device_tracker.iphone", STATE_ON, {"battery_level": "40"})])
    assert_entity_state(hass, "sensor.test_power", "20.00")


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

    await set_states(hass, [("light.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", STATE_UNAVAILABLE)


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
    await set_states(
        hass,
        [
            ("light.test", STATE_UNAVAILABLE),
            ("binary_sensor.test1", STATE_UNAVAILABLE),
            ("binary_sensor.test2", STATE_UNAVAILABLE),
            ("binary_sensor.test3", STATE_UNAVAILABLE),
        ],
    )
    await run_powercalc_setup(hass, sensor_config, {})

    await set_states(
        hass,
        [
            ("light.test", STATE_ON),
            ("binary_sensor.test1", STATE_OFF),
            ("binary_sensor.test2", STATE_ON),
            ("binary_sensor.test3", STATE_OFF),
        ],
    )
    assert_entity_state(hass, "sensor.test_power", "10.00")

    await set_states(hass, [("binary_sensor.test1", STATE_OFF), ("binary_sensor.test2", STATE_OFF), ("binary_sensor.test3", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "10.00")

    await set_states(hass, [("binary_sensor.test1", STATE_ON), ("binary_sensor.test2", STATE_OFF), ("binary_sensor.test3", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", STATE_UNAVAILABLE)


async def test_playbook(hass: HomeAssistant) -> None:
    dishwasher_mode_entity = "sensor.dishwasher_operating_mode"

    await set_states(hass, [(dishwasher_mode_entity, "Cycle Complete")])
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

    await set_states(hass, [(dishwasher_mode_entity, "Cycle Complete")])
    assert_entity_state(hass, "sensor.dishwasher_power", "9.60")

    await set_states(hass, [(dishwasher_mode_entity, "Cycle Paused")])
    assert_entity_state(hass, "sensor.dishwasher_power", "1.60")

    await set_states(hass, [(dishwasher_mode_entity, "Cycle Active")])
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=3))

    assert_entity_state(hass, "sensor.dishwasher_power", "20.00")

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=5))

    assert_entity_state(hass, "sensor.dishwasher_power", "40.00")

    await set_states(hass, [(dishwasher_mode_entity, "Cycle Complete")])
    assert_entity_state(hass, "sensor.dishwasher_power", "9.60")

    await set_states(hass, [(dishwasher_mode_entity, STATE_OFF)])
    assert_entity_state(hass, "sensor.dishwasher_power", "0.00")


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

    await set_states(hass, [("switch.test1", STATE_OFF), ("switch.test2", STATE_OFF), ("switch.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "4.00")

    await set_states(hass, [("switch.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "10.00")


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

    await set_states(hass, [("switch.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "1.00")


async def test_composite_strategy_from_library_profile(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("composite"),
        },
    )

    await set_states(hass, [("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})])
    assert_entity_state(hass, "sensor.test_power", "0.82")


async def test_composite_mode_sum(hass: HomeAssistant) -> None:
    await set_states(hass, [("sensor.test", 50)])
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

    await set_states(hass, [("light.test", STATE_ON, {ATTR_BRIGHTNESS: 200})])
    assert_entity_state(hass, "sensor.test_power", "30.00")


async def test_sum_mode_from_library_profile(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "sensor.test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("composite_sum"),
        },
    )

    await set_states(hass, [("sensor.test", "100")])
    assert_entity_state(hass, "sensor.test_power", "22.00")

    await set_states(hass, [("sensor.test", "20")])
    assert_entity_state(hass, "sensor.test_power", "2.00")


async def test_numeric_state_omit_entity_id(hass: HomeAssistant) -> None:
    await set_states(hass, [("sensor.test", 2000)])
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

    assert_entity_state(hass, "sensor.test_power", "1000.00")

    await set_states(hass, [("sensor.test", 100)])
    assert_entity_state(hass, "sensor.test_power", "500.00")


async def test_state_omit_entity_id(hass: HomeAssistant) -> None:
    await set_states(hass, [("media_player.test", STATE_PAUSED)])
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

    assert_entity_state(hass, "sensor.test_power", "500.00")

    await set_states(hass, [("media_player.test", STATE_PLAYING)])
    assert_entity_state(hass, "sensor.test_power", "1000.00")


async def test_state_attribute_entity_id(hass: HomeAssistant) -> None:
    await set_states(hass, [("media_player.test", STATE_PLAYING, {"source": "HDMI2"})])
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

    assert_entity_state(hass, "sensor.test_power", "2.00")

    await set_states(hass, [("media_player.test", STATE_PLAYING, {"source": "HDMI1"})])
    assert_entity_state(hass, "sensor.test_power", "20.00")


async def test_lut(hass: HomeAssistant) -> None:
    light_entity = "light.test"
    power_entity = "sensor.test_power"
    await run_powercalc_setup(hass, {CONF_ENTITY_ID: light_entity, CONF_MANUFACTURER: "test", CONF_MODEL: "composite_lut"})

    assert hass.states.get(power_entity)

    await set_states(hass, [(light_entity, STATE_ON, {ATTR_EFFECT: "Night light"})])
    assert_entity_state(hass, power_entity, "1.24")

    await set_states(hass, [(light_entity, STATE_ON, {ATTR_BRIGHTNESS: 128, ATTR_COLOR_MODE: ColorMode.BRIGHTNESS})])
    assert_entity_state(hass, power_entity, "128.00")
