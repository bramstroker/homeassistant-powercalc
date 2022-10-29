from decimal import Decimal

import pytest
from homeassistant.components import sensor
from homeassistant.const import CONF_PLATFORM, STATE_OFF, STATE_ON, DEVICE_CLASS_CURRENT
from homeassistant.core import HomeAssistant, State
from homeassistant.setup import async_setup_component

import custom_components.test.sensor as test_sensor_platform
from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CONF_POWER_FACTOR, CONF_VOLTAGE
from custom_components.powercalc.strategy.wled import WledStrategy
from custom_components.test.light import MockLight
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_registry,
)

from ..common import create_mock_light_entity


async def test_can_calculate_power(hass: HomeAssistant):
    await create_mock_light_entity(hass, MockLight("test", STATE_ON, "abc"))

    light_source_entity = await create_source_entity("light.test", hass)

    platform: test_sensor_platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    estimated_current_entity = platform.MockSensor(
        name="test_estimated_current", native_value="50.0", unique_id="abc"
    )
    platform.ENTITIES[0] = estimated_current_entity

    assert await async_setup_component(
        hass, sensor.DOMAIN, {sensor.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()

    strategy = WledStrategy(
        config={CONF_VOLTAGE: 5, CONF_POWER_FACTOR: 0.9},
        light_entity=light_source_entity,
        hass=hass,
        standby_power=0.1,
    )
    await strategy.validate_config()
    assert strategy.can_calculate_standby()

    state = State("sensor.test_estimated_current", "50.0")
    assert pytest.approx(0.225, 0.01) == float(await strategy.calculate(state))

    state = State("light.test", STATE_OFF)
    assert 0.1 == await strategy.calculate(state)

    state = State("light.test", STATE_ON)
    assert pytest.approx(0.225, 0.01) == float(await strategy.calculate(state))


async def test_find_estimated_current_entity_by_device_class(hass: HomeAssistant):
    """
    By default we will search for estimated_current entity by naming convention _estimated_current
    When none is found we check for entities on the same WLED device with device_class current
    """
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="wled-device-id"
            ),
            "sensor.test_current": RegistryEntry(
                entity_id="sensor.test_current",
                unique_id="1234",
                platform="sensor",
                device_id="wled-device-id",
                unit_of_measurement="mA",
                device_class=DEVICE_CLASS_CURRENT
            ),
        },
    )

    strategy = WledStrategy(
        config={CONF_VOLTAGE: 5, CONF_POWER_FACTOR: 0.9},
        light_entity=await create_source_entity("light.test", hass),
        hass=hass,
        standby_power=0.1,
    )
    estimated_current_entity = await strategy.find_estimated_current_entity()
    assert estimated_current_entity == "sensor.test_current"
