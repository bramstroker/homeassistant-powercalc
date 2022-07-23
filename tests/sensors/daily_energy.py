from homeassistant.core import HomeAssistant

from homeassistant.const import (
    CONF_NAME
)

from custom_components.powercalc.sensors.daily_energy import (
    create_daily_fixed_energy_sensor
)

async def test_create_daily_energy_sensor(hass: HomeAssistant):
    sensor_config = {
        CONF_NAME: "My sensor"
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)
    assert sensor
    assert sensor.name == "My sensor"