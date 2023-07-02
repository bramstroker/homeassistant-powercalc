import logging

import pytest
from homeassistant.components import utility_meter
from homeassistant.components.utility_meter.sensor import (
    ATTR_SOURCE_ID,
    ATTR_STATUS,
    ATTR_TARIFF,
    COLLECTING,
    CONF_UNIQUE_ID,
    PAUSED,
)
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_registry

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_ID,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    CalculationStrategy,
)
from tests.common import create_input_boolean, run_powercalc_setup


async def test_tariff_sensors_are_created(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    assert await async_setup_component(hass, utility_meter.DOMAIN, {})

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TARIFFS: ["general", "peak", "offpeak"],
            CONF_UTILITY_METER_TYPES: ["daily"],
        },
    )

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

    general_sensor = hass.states.get("sensor.test_energy_daily")
    assert general_sensor
    assert offpeak_sensor.attributes[ATTR_SOURCE_ID] == "sensor.test_energy"


async def test_utility_meter_is_not_created_twice(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    power_sensor_id = "sensor.test_power"
    energy_sensor_id = "sensor.test_energy"
    utility_meter_id = "sensor.test_energy_daily"
    entity_registry = mock_registry(
        hass,
        {
            power_sensor_id: RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="1234",
                name="Test power",
                platform="powercalc",
            ),
            energy_sensor_id: RegistryEntry(
                entity_id=energy_sensor_id,
                unique_id="1234_energy",
                name="Test energy",
                platform="powercalc",
            ),
            utility_meter_id: RegistryEntry(
                entity_id=utility_meter_id,
                unique_id="1234_energy_daily",
                name="Test energy daily",
                platform="powercalc",
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_UNIQUE_ID: "1234",
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: ["daily"],
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_SENSOR_ID: energy_sensor_id,
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_UNIQUE_ID: "1234",
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: ["daily"],
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_SENSOR_ID: energy_sensor_id,
        },
    )

    assert entity_registry.async_get(utility_meter_id)
    assert hass.states.get(utility_meter_id)
    assert len(caplog.records) == 0
