from datetime import timedelta
import logging
from unittest.mock import patch

from freezegun import freeze_time
from homeassistant.components import utility_meter
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.utility_meter.const import DAILY, HOURLY
from homeassistant.components.utility_meter.sensor import (
    ATTR_STATUS,
    ATTR_TARIFF,
    COLLECTING,
    CONF_UNIQUE_ID,
    PAUSED,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_ENTITY_ID, CONF_NAME, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.setup import async_setup_component
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    RegistryEntryWithDefaults,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_SENSOR_TYPE,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    CalculationStrategy,
    SensorType,
)
from tests.common import create_input_boolean, create_mocked_virtual_power_sensor_entry, run_powercalc_setup, setup_config_entry


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
            CONF_UTILITY_METER_TYPES: [DAILY, HOURLY],
        },
    )

    tariff_select = hass.states.get("select.test_energy_daily")
    assert tariff_select
    assert tariff_select.state == "peak"

    peak_sensor = hass.states.get("sensor.test_energy_daily_peak")
    assert peak_sensor
    assert peak_sensor.attributes[ATTR_TARIFF] == "peak"
    assert peak_sensor.attributes[ATTR_STATUS] == COLLECTING

    offpeak_sensor = hass.states.get("sensor.test_energy_daily_offpeak")
    assert offpeak_sensor
    assert offpeak_sensor.attributes[ATTR_TARIFF] == "offpeak"
    assert offpeak_sensor.attributes[ATTR_STATUS] == PAUSED

    general_sensor_daily = hass.states.get("sensor.test_energy_daily")
    assert general_sensor_daily

    general_sensor_hourly = hass.states.get("sensor.test_energy_hourly")
    assert general_sensor_hourly

    tariff_select = hass.states.get("select.test_energy_daily")
    assert tariff_select
    assert tariff_select.state == "peak"

    hass.states.async_set("select.test_energy_daily", "offpeak")
    await hass.async_block_till_done()

    peak_sensor = hass.states.get("sensor.test_energy_daily_peak")
    assert peak_sensor.attributes[ATTR_STATUS] == PAUSED

    offpeak_sensor = hass.states.get("sensor.test_energy_daily_offpeak")
    assert offpeak_sensor.attributes[ATTR_STATUS] == COLLECTING


async def test_tariff_sensors_created_for_gui_sensors(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    entry1 = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.test",
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
        title="Entry1",
    )

    entry2 = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.test2",
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
        title="Entry2",
    )

    tariff_select = hass.states.get("select.test_energy_daily")
    assert tariff_select
    assert tariff_select.state == "peak"

    registry_entry = entity_registry.async_get("select.test_energy_daily")
    assert registry_entry
    assert registry_entry.platform == DOMAIN
    assert registry_entry.config_entry_id == entry1.entry_id

    registry_entry = entity_registry.async_get("select.test2_energy_daily")
    assert registry_entry
    assert registry_entry.platform == DOMAIN
    assert registry_entry.config_entry_id == entry2.entry_id


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
            power_sensor_id: RegistryEntryWithDefaults(
                entity_id=power_sensor_id,
                unique_id="1234",
                name="Test power",
                platform="powercalc",
            ),
            energy_sensor_id: RegistryEntryWithDefaults(
                entity_id=energy_sensor_id,
                unique_id="1234_energy",
                name="Test energy",
                platform="powercalc",
            ),
            utility_meter_id: RegistryEntryWithDefaults(
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
            CONF_UTILITY_METER_TYPES: [DAILY],
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_SENSOR_ID: energy_sensor_id,
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_UNIQUE_ID: "1234",
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY],
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_SENSOR_ID: energy_sensor_id,
        },
    )

    assert entity_registry.async_get(utility_meter_id)
    assert hass.states.get(utility_meter_id)
    assert len(caplog.records) == 0


async def test_rounding_digits(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    """Test that the rounding digits configuration `energy_sensor_precision` is respected."""
    await create_mocked_virtual_power_sensor_entry(
        hass,
        unique_id="1234",
        extra_config={
            CONF_CREATE_UTILITY_METERS: True,
            CONF_ENERGY_SENSOR_PRECISION: 2,
        },
    )

    hass.states.async_set("sensor.test_energy", 1, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})
    await hass.async_block_till_done()

    now = dt_util.utcnow() + timedelta(seconds=10)
    with freeze_time(now):
        hass.states.async_set(
            "sensor.test_energy",
            3,
            {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    registry_entry = entity_registry.async_get("sensor.test_energy_daily")
    assert registry_entry
    assert registry_entry.options == {"sensor": {"suggested_display_precision": 2}}

    state = hass.states.get("sensor.test_energy_daily")
    assert state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
    assert state.state == "2.00"


async def test_regression(hass: HomeAssistant) -> None:
    # - entity_id: switch.gerateschranke_licht_servodrive
    # name: Geräteschrank
    # power_sensor_id: sensor.gerateschranke_licht_servodrive_power
    # - entity_id: switch.gerateschranke_frei
    #  name: Geräteschrank unbenutzt
    #  power_sensor_id: sensor.gerateschranke_frei_power
    power_sensor_id = "sensor.test_power"
    power_sensor2_id = "sensor.test2_power"
    energy_sensor_id = "sensor.test_energy"
    device_id = "some_device"
    mock_registry(
        hass,
        {
            power_sensor_id: RegistryEntryWithDefaults(
                entity_id=power_sensor_id,
                unique_id="29742725-6F34-49F2-91DE-589951306E9F",
                name="Test power",
                platform="sensor",
                device_id=device_id,
            ),
            power_sensor2_id: RegistryEntryWithDefaults(
                entity_id=power_sensor_id,
                unique_id="A1CBB81F-A958-482B-A10E-1DAA0652796A",
                name="Test power2",
                platform="sensor",
                device_id=device_id,
            ),
            energy_sensor_id: RegistryEntryWithDefaults(
                entity_id=energy_sensor_id,
                unique_id="4FA9B62F-E957-4366-B7DA-832C1D5F742D",
                name="Test energy",
                platform="sensor",
                device_id=device_id,
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="foo",
                model="bar",
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_POWER_SENSOR_ID: power_sensor_id,
                CONF_NAME: "Test1",
            },
            {
                CONF_POWER_SENSOR_ID: power_sensor2_id,
                CONF_NAME: "Test2",
            },
        ],
        {
            CONF_CREATE_UTILITY_METERS: True,
        },
    )


async def test_net_consumption_option(hass: HomeAssistant) -> None:
    """Test that the net consumption option is respected."""
    with patch("custom_components.powercalc.sensors.utility_meter.VirtualUtilityMeter") as mock_utility_meter:
        await run_powercalc_setup(
            hass,
            {
                CONF_ENTITY_ID: "switch.test",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 50},
                CONF_CREATE_UTILITY_METERS: True,
                CONF_UTILITY_METER_NET_CONSUMPTION: True,
            },
        )

        _, kwargs = mock_utility_meter.call_args
        assert kwargs["net_consumption"] is True
