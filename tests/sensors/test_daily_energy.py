from datetime import timedelta

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR,
    ENERGY_WATT_HOUR,
    POWER_WATT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt

from custom_components.powercalc.const import (
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ON_TIME,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    DOMAIN,
    UnitPrefix,
)
from custom_components.powercalc.sensors.daily_energy import (
    create_daily_fixed_energy_sensor,
)

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from ..common import run_powercalc_setup_yaml_config


async def test_create_daily_energy_sensor_default_options(hass: HomeAssistant):
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_DAILY_FIXED_ENERGY: {},
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)
    assert sensor
    assert sensor.name == "My sensor Energy"
    assert sensor.entity_id == "sensor.my_sensor_energy"
    assert sensor._attr_native_unit_of_measurement == ENERGY_KILO_WATT_HOUR
    assert sensor.device_class == SensorDeviceClass.ENERGY
    assert sensor.state_class == SensorStateClass.TOTAL


@pytest.mark.parametrize(
    "unit_prefix,unit_of_measurement",
    [
        (UnitPrefix.NONE, ENERGY_WATT_HOUR),
        (UnitPrefix.KILO, ENERGY_KILO_WATT_HOUR),
        (UnitPrefix.MEGA, ENERGY_MEGA_WATT_HOUR),
    ],
)
async def test_create_daily_energy_sensor_unit_prefix_watt(
    hass: HomeAssistant, unit_prefix: str, unit_of_measurement: str
):
    """Test that setting the unit_prefix results in the correct unit_of_measurement"""
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_ENERGY_SENSOR_UNIT_PREFIX: unit_prefix,
        CONF_DAILY_FIXED_ENERGY: {},
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)
    assert sensor
    assert sensor.name == "My sensor Energy"
    assert sensor._attr_native_unit_of_measurement == unit_of_measurement


async def test_daily_energy_sensor_from_kwh_value(hass: HomeAssistant):
    update_frequency = 1800
    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_UPDATE_FREQUENCY: update_frequency,
                CONF_VALUE: 12,
            },
        },
    )

    sensor_entity_id = "sensor.ip_camera_upstairs_energy"
    state = hass.states.get(sensor_entity_id)
    assert state
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    # Trigger calculation in the future
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=update_frequency))
    await hass.async_block_till_done()

    state = hass.states.get(sensor_entity_id)
    assert state.state == "0.2500"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=update_frequency))
    await hass.async_block_till_done()

    state = hass.states.get(sensor_entity_id)
    assert state.state == "0.5000"


async def test_daily_energy_sensor_also_creates_power_sensor(hass: HomeAssistant):
    """
    When the user configured the value in W and the on_time is always on,
    then a power sensor should also be created
    """
    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 15,
                CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
            },
        },
    )

    state = hass.states.get("sensor.ip_camera_upstairs_energy")
    assert state
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    state = hass.states.get("sensor.ip_camera_upstairs_power")
    assert state
    assert state.state == "15.00"
    assert state.name == "IP camera upstairs power"


@pytest.mark.parametrize(
    "daily_fixed_options,elapsed_seconds,expected_delta",
    [
        (
            {
                CONF_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
                CONF_ON_TIME: timedelta(days=1),
                CONF_VALUE: 12,
            },
            3600,
            0.5,
        ),
        (
            # Consume 1500 x 2 hour = 3 kWh a day
            {
                CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
                CONF_ON_TIME: timedelta(hours=2),
                CONF_VALUE: 2000,
            },
            1200,  # Simulate 20 minutes
            0.0555,
        ),
        (
            {
                CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
                CONF_ON_TIME: 3600, # Test that on time can be passed as seconds
                CONF_VALUE: 2400
            },
            1800, # Simulate 30 minutes
            0.05
        ),
    ],
)
async def test_calculate_delta(
    hass: HomeAssistant,
    daily_fixed_options: ConfigType,
    elapsed_seconds: int,
    expected_delta: float,
):
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_DAILY_FIXED_ENERGY: daily_fixed_options,
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)

    delta = sensor.calculate_delta(elapsed_seconds)
    assert expected_delta == pytest.approx(float(delta), 0.001)

async def test_calculate_delta_mega_watt_hour(hass: HomeAssistant):
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.MEGA,
        CONF_DAILY_FIXED_ENERGY: {
            CONF_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
            CONF_ON_TIME: timedelta(days=1),
            CONF_VALUE: 12
        },
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)

    # Calculate delta after 1 hour
    delta = sensor.calculate_delta(3600)
    assert 0.0005 == pytest.approx(float(delta), 0.001)
