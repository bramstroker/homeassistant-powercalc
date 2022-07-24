import logging

import pytest
from homeassistant.components import input_boolean, light, sensor
from homeassistant.components.integration.sensor import ATTR_SOURCE_ID
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.utility_meter.sensor import ATTR_PERIOD, DAILY, HOURLY
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_UNIQUE_ID,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

import custom_components.test.light as test_light_platform
from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENTITIES,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_UTILITY_METER_TYPES,
    CONF_VALUE,
    DOMAIN,
    CalculationStrategy,
)

from .common import create_mock_light_entity, run_powercalc_setup_yaml_config


async def test_fixed_power_sensor_from_yaml(hass: HomeAssistant):
    source_entity = "input_boolean.test"
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )

    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: source_entity,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    state = hass.states.get("sensor.test_power")
    assert state.state == "0.00"

    hass.states.async_set(source_entity, STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "50.00"
    assert (
        power_state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.FIXED
    )
    assert power_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER

    energy_state = hass.states.get("sensor.test_energy")
    assert energy_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert (
        energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR
    )
    assert energy_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_power"
    assert energy_state.attributes.get(ATTR_SOURCE_ENTITY) == "input_boolean.test"


async def test_utility_meter_is_created(hass: HomeAssistant):
    """Test that utility meters are succesfully created when `create_utility_meter: true`"""
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY, HOURLY],
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    daily_state = hass.states.get("sensor.test_energy_daily")
    assert daily_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_energy"
    assert daily_state.attributes.get(ATTR_PERIOD) == DAILY

    hourly_state = hass.states.get("sensor.test_energy_hourly")
    assert hourly_state
    assert hourly_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_energy"
    assert hourly_state.attributes.get(ATTR_PERIOD) == HOURLY

    monthly_state = hass.states.get("sensor.test_energy_monthly")
    assert not monthly_state


async def test_create_nested_group_sensor(hass: HomeAssistant):
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test1": None}}
    )
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test2": None}}
    )

    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_CREATE_GROUP: "TestGroup1",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 50},
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test1",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 50},
                },
                {
                    CONF_CREATE_GROUP: "TestGroup2",
                    CONF_ENTITIES: [
                        {
                            CONF_ENTITY_ID: "input_boolean.test2",
                            CONF_MODE: CalculationStrategy.FIXED,
                            CONF_FIXED: {CONF_POWER: 50},
                        },
                    ],
                },
            ],
        },
    )

    hass.states.async_set("input_boolean.test", STATE_ON)
    hass.states.async_set("input_boolean.test1", STATE_ON)
    hass.states.async_set("input_boolean.test2", STATE_ON)

    await hass.async_block_till_done()

    group1 = hass.states.get("sensor.testgroup1_power")
    assert group1.attributes[ATTR_ENTITIES] == {
        "sensor.test_power",
        "sensor.test1_power",
        "sensor.test2_power",
    }
    assert group1.state == "150.00"

    group2 = hass.states.get("sensor.testgroup2_power")
    assert group2.attributes[ATTR_ENTITIES] == {
        "sensor.test2_power",
    }
    assert group2.state == "50.00"

    hass.states.async_set("input_boolean.test2", STATE_OFF)
    await hass.async_block_till_done()

    group1 = hass.states.get("sensor.testgroup1_power")
    assert group1.state == "100.00"

    group2 = hass.states.get("sensor.testgroup2_power")
    assert group2.state == "0.00"


async def test_light_lut_strategy(hass: HomeAssistant):
    light_entity = test_light_platform.MockLight(
        "test1",
        STATE_ON,
        unique_id="dsafbwq",
    )
    light_entity.supported_color_modes = {light.ColorMode.BRIGHTNESS}
    light_entity.color_mode = light.ColorMode.BRIGHTNESS
    light_entity.brightness = 125
    light_entity.manufacturer = "signify"
    light_entity.model = "LWB010"

    (light_entity_id, __) = await create_mock_light_entity(hass, light_entity)

    await run_powercalc_setup_yaml_config(
        hass, {CONF_PLATFORM: DOMAIN, CONF_ENTITY_ID: light_entity_id}
    )

    state = hass.states.get("sensor.test1_power")
    assert state
    assert state.state == "2.67"
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER
    assert state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.LUT
    assert state.attributes.get(ATTR_SOURCE_ENTITY) == light_entity_id


async def test_error_when_configuring_same_entity_twice(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    await _create_input_boolean_entity(hass, "test")

    await run_powercalc_setup_yaml_config(
        hass,
        [
            {
                CONF_PLATFORM: DOMAIN,
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 50},
            },
            {
                CONF_PLATFORM: DOMAIN,
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 100},
            },
        ],
    )

    assert "This entity has already configured a power sensor" in caplog.text
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_can_create_same_entity_twice_with_unique_id(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    await _create_input_boolean_entity(hass, "test")

    await run_powercalc_setup_yaml_config(
        hass,
        [
            {
                CONF_PLATFORM: DOMAIN,
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_UNIQUE_ID: "111",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 50},
            },
            {
                CONF_PLATFORM: DOMAIN,
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_UNIQUE_ID: "222",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 100},
            },
        ],
    )

    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")
    assert hass.states.get("sensor.test_power_2")
    assert hass.states.get("sensor.test_energy_2")


async def _create_input_boolean_entity(hass: HomeAssistant, name: str):
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {name: None}}
    )

    await hass.async_block_till_done()
