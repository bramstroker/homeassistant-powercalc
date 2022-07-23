import imp
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
from homeassistant.helpers import config_validation as device_registry
from homeassistant.loader import DATA_COMPONENTS, DATA_INTEGRATIONS
from homeassistant.setup import async_setup_component
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components import (
    light,
    input_boolean,
    sensor
)
from homeassistant.helpers.entity_platform import split_entity_id
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    MockPlatform,
    mock_registry,
    mock_device_registry
)
from custom_components.powercalc.const import ATTR_CALCULATION_MODE, ATTR_ENTITIES, ATTR_SOURCE_ENTITY, CONF_CREATE_GROUP, CONF_FIXED, CONF_MODE, CONF_POWER, DOMAIN, CalculationStrategy
import custom_components.test.light as test_light_platform

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
    assert state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.FIXED

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

    light_entity_id = await _create_mock_light_entity(hass, light_entity)

    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {sensor.DOMAIN: {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: light_entity_id
        }}
    )

    await hass.async_block_till_done()

    state = hass.states.get("sensor.test1_power")
    assert state
    assert state.state == "2.67"
    assert state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.LUT
    assert state.attributes.get(ATTR_SOURCE_ENTITY) == light_entity_id

async def _create_mock_light_entity(
    hass: HomeAssistant,
    light_entity: test_light_platform.MockLight
) -> str:
    """Create a mocked light entity, and bind it to a device having a manufacturer/model"""
    entity_registry = mock_registry(hass)
    device_registry = mock_device_registry(hass)
    platform: test_light_platform = getattr(hass.components, "test.light")
    platform.init(empty=True)

    platform.ENTITIES.append(light_entity)

    assert await async_setup_component(
        hass, light.DOMAIN, {light.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("dummy", light_entity.unique_id)},
        manufacturer=light_entity.manufacturer,
        model=light_entity.model
    )
    
    entity_entry = entity_registry.async_get_or_create(
        "light", "test", light_entity.unique_id, device_id=device_entry.id
    )
    return entity_entry.entity_id