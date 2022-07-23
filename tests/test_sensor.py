import sys
import importlib
from homeassistant.core import HomeAssistant, CoreState
from homeassistant.const import (
    CONF_PLATFORM,
    CONF_ENTITY_ID,
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    CONF_ENTITIES,
    CONF_UNIQUE_ID,
    STATE_ON,
)
from homeassistant.loader import DATA_COMPONENTS, DATA_INTEGRATIONS
from homeassistant.setup import async_setup_component
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components import (
    light,
    input_boolean,
    sensor
)
from homeassistant.helpers.entity_platform import split_entity_id

from pytest_homeassistant_custom_component.common import mock_entity_platform
from custom_components.powercalc.const import ATTR_ENTITIES, CONF_CREATE_GROUP, CONF_FIXED, CONF_MODE, CONF_POWER, DOMAIN, CalculationStrategy

async def test_fixed_power_sensor_from_yaml(hass: HomeAssistant, enable_custom_integrations):
    source_entity = "input_boolean.test"
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    
    await hass.async_block_till_done()

    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {sensor.DOMAIN: {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: source_entity,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {
                CONF_POWER: 50
            }
        }}
    )
    await hass.async_block_till_done()
    
    state = hass.states.get("sensor.test_power")
    assert state.state == "0.00"

    hass.states.async_set(source_entity, STATE_ON)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state.state == "50.00"

    assert hass.states.get("sensor.test_energy")

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

    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {
            sensor.DOMAIN: {
                CONF_PLATFORM: DOMAIN,
                CONF_CREATE_GROUP: "TestGroup1",
                CONF_ENTITIES: [
                    {
                        CONF_ENTITY_ID: "input_boolean.test",
                        CONF_MODE: CalculationStrategy.FIXED,
                        CONF_FIXED: {
                            CONF_POWER: 50
                        }
                    },
                    {
                        CONF_ENTITY_ID: "input_boolean.test1", 
                        CONF_MODE: CalculationStrategy.FIXED,
                        CONF_FIXED: {
                            CONF_POWER: 50
                        }
                    },
                    {
                        CONF_CREATE_GROUP: "TestGroup2",
                        CONF_ENTITIES: [
                            {
                                CONF_ENTITY_ID: "input_boolean.test2", 
                                CONF_MODE: CalculationStrategy.FIXED,
                                CONF_FIXED: {
                                    CONF_POWER: 50
                                }
                            },
                        ]
                    }
                ]
            }
        }
    )
    await hass.async_block_till_done()

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

async def test_light(hass: HomeAssistant, enable_custom_integrations):
    platform = getattr(hass.components, "test.light")
    platform.init(empty=True)

    platform.ENTITIES.append(platform.MockLight("test1", STATE_ON))
    platform.ENTITIES.append(platform.MockLight("test2", STATE_ON))
    assert await async_setup_component(
        hass, light.DOMAIN, {light.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.test1")
    assert state
    assert state.state == STATE_ON

    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {sensor.DOMAIN: {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: "light.test1",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {
                CONF_POWER: 50
            }
        }}
    )

    await hass.async_block_till_done()

    state = hass.states.get("sensor.test1_power")
    assert state
    assert state.state == "50.00"