from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_PLATFORM, CONF_ENTITY_ID, ATTR_ENTITY_ID, SERVICE_TURN_ON
from homeassistant.setup import async_setup_component
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components import (
    input_boolean,
    sensor
)

from pytest_homeassistant_custom_component.common import mock_entity_platform
from custom_components.powercalc.const import CONF_FIXED, CONF_MODE, CONF_POWER, DOMAIN, CalculationStrategy

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

    await hass.services.async_call(
        input_boolean.DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: source_entity},
        blocking=True,
    )

    state = hass.states.get("sensor.test_power")
    assert state.state == "50.00"