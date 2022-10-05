from homeassistant.components import input_boolean, sensor, utility_meter
from homeassistant.components.utility_meter.sensor import (
    ATTR_SOURCE_ID,
    ATTR_STATUS,
    ATTR_TARIFF,
    COLLECTING,
    PAUSED,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    CalculationStrategy,
)
from ..common import create_input_boolean


async def test_tariff_sensors_are_created(hass: HomeAssistant):
    await create_input_boolean(hass)

    assert await async_setup_component(hass, utility_meter.DOMAIN, {})

    await hass.async_block_till_done()

    await async_setup_component(
        hass,
        sensor.DOMAIN,
        {
            sensor.DOMAIN: [
                {
                    CONF_PLATFORM: DOMAIN,
                    CONF_ENTITY_ID: "input_boolean.test",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 50},
                    CONF_CREATE_UTILITY_METERS: True,
                    CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
                    CONF_UTILITY_METER_TYPES: ["daily"],
                }
            ]
        },
    )
    await hass.async_block_till_done()

    tariff_select = hass.states.get("select.test_energy_daily")
    assert tariff_select
    assert tariff_select.state == "peak"

    peak_sensor = hass.states.get("sensor.test_energy_daily_peak")
    assert peak_sensor
    assert peak_sensor.attributes[ATTR_SOURCE_ID] == "sensor.test_energy"
    assert peak_sensor.attributes[ATTR_TARIFF] == "peak"
    assert peak_sensor.attributes[ATTR_STATUS] == COLLECTING

    offpeak_sensor = hass.states.get("sensor.test_energy_daily_offpeak")
    assert offpeak_sensor
    assert offpeak_sensor.attributes[ATTR_SOURCE_ID] == "sensor.test_energy"
    assert offpeak_sensor.attributes[ATTR_TARIFF] == "offpeak"
    assert offpeak_sensor.attributes[ATTR_STATUS] == PAUSED
