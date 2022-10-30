import logging
from datetime import timedelta

import pytest
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.components.vacuum import (
    ATTR_BATTERY_LEVEL,
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_RETURNING,
)
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import EVENT_HOMEASSISTANT_START, CoreState, HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    MockEntity,
    MockEntityPlatform,
    async_fire_time_changed,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CALIBRATE,
    CONF_CREATE_GROUP,
    CONF_DELAY,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_UNAVAILABLE_POWER,
    DOMAIN,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
)

from ..common import (
    create_input_boolean,
    create_input_number,
    get_simple_fixed_config,
    run_powercalc_setup_yaml_config,
)


async def test_use_real_power_sensor_in_group(hass: HomeAssistant):
    await create_input_boolean(hass)

    platform = MockEntityPlatform(hass)
    entity = MockEntity(
        name="existing_power", unique_id="1234", device_class=SensorDeviceClass.POWER
    )
    await platform.async_add_entities([entity])

    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_POWER_SENSOR_ID: "sensor.existing_power",
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 50},
                },
            ],
        },
    )

    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.testgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
        "sensor.test_power",
    }


async def test_rounding_precision(hass: HomeAssistant):
    await create_input_boolean(hass)

    config = {CONF_POWER_SENSOR_PRECISION: 4}
    await async_setup_component(hass, DOMAIN, {DOMAIN: config})

    await run_powercalc_setup_yaml_config(
        hass,
        get_simple_fixed_config("input_boolean.test", 50),
    )

    state = hass.states.get("sensor.test_power")
    assert state.state == "0.0000"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "50.0000"


async def test_initial_state_is_calculated_after_startup(hass: HomeAssistant):
    """
    The initial state of the power sensor should be calculated after HA startup completes.
    When we do it already during powercalc setup some entities referred in template could be unknown yet
    """
    hass.state = CoreState.not_running

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Henkie",
            CONF_FIXED: {CONF_POWER: "{{states('input_number.test')}}"},
        },
    )

    await create_input_number(hass, "test", 30)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henkie_power").state == "30.00"


async def test_standby_power(hass: HomeAssistant):
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 0.5,
            CONF_FIXED: {CONF_POWER: 15},
        },
    )

    hass.states.async_set("input_boolean.test", STATE_OFF)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "0.50"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "15.00"


async def test_multiply_factor(hass: HomeAssistant):
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 0.2,
            CONF_MULTIPLY_FACTOR_STANDBY: True,
            CONF_MULTIPLY_FACTOR: 3,
            CONF_FIXED: {CONF_POWER: 5},
        },
    )

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "0.60"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "15.00"


async def test_error_when_no_strategy_has_been_configured(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        {CONF_ENTITY_ID: "input_boolean.test"},
    )

    assert "Skipping sensor setup" in caplog.text


async def test_strategy_enabled_condition(hass: HomeAssistant):
    """
    Test calculation_enabled_condition is working correctly.
    This is used for example on robot vacuum cleaners.
    This test simulates a vacuum cleaner going through following stages:
     - cleaning
     - returning
     - docked
    When the state is docked the calculation is activated and linear calibration is used to map the consumption while charging
    """
    vacuum_entity_id = "vacuum.my_robot_cleaner"
    power_entity_id = "sensor.my_robot_cleaner_power"

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: vacuum_entity_id,
            CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
            CONF_LINEAR: {
                CONF_ATTRIBUTE: "battery_level",
                CONF_CALIBRATE: [
                    "1 -> 20",
                    "79 -> 20",
                    "80 -> 15",
                    "99 -> 8",
                    "100 -> 1.5",
                ],
            },
        },
    )

    assert hass.states.get(power_entity_id)

    hass.states.async_set(vacuum_entity_id, STATE_CLEANING, {ATTR_BATTERY_LEVEL: 40})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "0.00"

    hass.states.async_set(vacuum_entity_id, STATE_RETURNING, {ATTR_BATTERY_LEVEL: 40})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "0.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 20})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 60})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 80})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "15.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 100})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "1.50"


async def test_template_entity_tracking(hass: HomeAssistant) -> None:
    await create_input_number(hass, "test", 0)
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {CONF_POWER: "{{ states('input_number.test') }}"},
        },
    )

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"

    hass.states.async_set("input_number.test", 15)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "15.00"


async def test_unknown_source_entity_state(hass: HomeAssistant):
    """Power sensor should be unavailable when source entity state is unknown"""
    await create_input_boolean(hass)
    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {CONF_POWER: 20},
        },
    )
    hass.states.async_set("input_boolean.test", STATE_UNKNOWN)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE


async def test_error_when_model_not_supported(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)

    await create_input_boolean(hass)
    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MANUFACTURER: "Foo",
            CONF_MODEL: "Bar",
        },
    )

    assert not hass.states.get("sensor.test_power")

    assert "Skipping sensor setup" in caplog.text


async def test_sleep_power(hass: HomeAssistant):
    """Test sleep power for devices having a sleep mode"""
    entity_id = "media_player.test"
    power_entity_id = "sensor.test_power"

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_STANDBY_POWER: 20,
            CONF_SLEEP_POWER: {CONF_POWER: 5, CONF_DELAY: 10},
            CONF_FIXED: {CONF_POWER: 100},
        },
    )

    hass.states.async_set(entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    # After 10 seconds the device goes into sleep mode, check the sleep power is set on the power sensor
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "5.00"

    hass.states.async_set(entity_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "100.00"

    hass.states.async_set(entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    # Check that the sleepmode timer is reset correctly when the device goes to a non OFF state again
    hass.states.async_set(entity_id, STATE_ON)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=20))
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "100.00"


async def test_unavailable_power(hass: HomeAssistant):
    """Test specifying an alternative power value if the source entity is unavailable"""
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 20,
            CONF_UNAVAILABLE_POWER: 0,
            CONF_FIXED: {CONF_POWER: 100},
        },
    )

    hass.states.async_set("input_boolean.test", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"
