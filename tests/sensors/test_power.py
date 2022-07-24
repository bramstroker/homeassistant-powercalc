from homeassistant.components import input_boolean, sensor
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockEntity, MockEntityPlatform

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CREATE_GROUP,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    DOMAIN,
    CalculationStrategy,
)


async def test_use_real_power_sensor_in_group(hass: HomeAssistant):
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )

    platform = MockEntityPlatform(hass)
    entity = MockEntity(
        name="existing_power", unique_id="1234", device_class=SensorDeviceClass.POWER
    )
    await platform.async_add_entities([entity])

    await hass.async_block_till_done()

    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {
            sensor.DOMAIN: {
                CONF_PLATFORM: DOMAIN,
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
            }
        },
    )

    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.testgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
        "sensor.test_power",
    }
