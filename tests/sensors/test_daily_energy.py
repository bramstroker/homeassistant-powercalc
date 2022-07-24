from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_NAME, ENERGY_KILO_WATT_HOUR, ENERGY_WATT_HOUR
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ON_TIME,
    UnitPrefix,
)
from custom_components.powercalc.sensors.daily_energy import (
    create_daily_fixed_energy_sensor,
)


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


async def test_create_daily_energy_sensor_unit_prefix_watt(hass: HomeAssistant):
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE,
        CONF_DAILY_FIXED_ENERGY: {},
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)
    assert sensor
    assert sensor.name == "My sensor Energy"
    assert sensor._attr_native_unit_of_measurement == ENERGY_WATT_HOUR
