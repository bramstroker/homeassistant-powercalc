from homeassistant.core import HomeAssistant
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    CONF_PLATFORM,
    CONF_ENTITY_ID,
    CONF_ENTITIES,
    STATE_ON,
    ATTR_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER
)
from homeassistant.setup import async_setup_component
from homeassistant.components import (
    light,
    input_boolean,
    sensor,
)
from homeassistant.helpers.typing import ConfigType

from homeassistant.components.integration.sensor import ATTR_SOURCE_ID
from homeassistant.components.utility_meter.sensor import (
    ATTR_PERIOD,
    DAILY, 
    HOURLY
)

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_registry,
    mock_device_registry
)
from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENTITIES,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    CalculationStrategy
)
import custom_components.test.light as test_light_platform

async def test_fixed_power_sensor_from_yaml(hass: HomeAssistant):
    source_entity = "input_boolean.test"
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    
    await hass.async_block_till_done()

    await _run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: source_entity,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {
                CONF_POWER: 50
            }
        }
    )

    state = hass.states.get("sensor.test_power")
    assert state.state == "0.00"

    hass.states.async_set(source_entity, STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "50.00"
    assert power_state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.FIXED
    assert power_state.attributes.get(ATTR_DEVICE_CLASS) == DEVICE_CLASS_POWER

    energy_state = hass.states.get("sensor.test_energy")
    assert energy_state.attributes.get(ATTR_DEVICE_CLASS) == DEVICE_CLASS_ENERGY
    assert energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR
    assert energy_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_power"
    assert energy_state.attributes.get(ATTR_SOURCE_ENTITY) == "input_boolean.test"

async def test_utility_meter_is_created(hass: HomeAssistant):
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    await hass.async_block_till_done()

    await _run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY, HOURLY],
            CONF_FIXED: {
                CONF_POWER: 50
            }
        }
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

    await _run_powercalc_setup_yaml_config(
        hass,
        {
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

    await _run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_ENTITY_ID: light_entity_id
        }
    )

    state = hass.states.get("sensor.test1_power")
    assert state
    assert state.state == "2.67"
    assert state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.LUT
    assert state.attributes.get(ATTR_SOURCE_ENTITY) == light_entity_id

async def _run_powercalc_setup_yaml_config(hass: HomeAssistant, config: ConfigType):
    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {sensor.DOMAIN: config}
    )
    await hass.async_block_till_done()

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