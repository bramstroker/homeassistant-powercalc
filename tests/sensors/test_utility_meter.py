from datetime import timedelta
import logging
from unittest.mock import PropertyMock, patch

from freezegun import freeze_time
from homeassistant.components import utility_meter
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.utility_meter.const import DAILY, HOURLY, QUARTER_HOURLY
from homeassistant.components.utility_meter.select import TariffSelect
from homeassistant.components.utility_meter.sensor import (
    ATTR_STATUS,
    ATTR_TARIFF,
    COLLECTING,
    CONF_UNIQUE_ID,
    PAUSED,
)
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.setup import async_setup_component
import homeassistant.util.dt as dt_util
import pytest

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
from tests.common import (
    assert_entity_state,
    create_mock_config_entry,
    create_mocked_virtual_power_sensor_entry,
    mock_device,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)


async def setup_existing_energy_tariff_meters(hass: HomeAssistant) -> None:
    """Set up tariff meters backed by registered power and energy sensors."""
    mock_entities_in_registry(
        hass,
        {
            "sensor.existing_power": {"name": "Existing power", "device_class": SensorDeviceClass.POWER},
            "sensor.existing_energy": {"name": "Existing energy", "device_class": SensorDeviceClass.ENERGY},
        },
    )
    await set_states(
        hass,
        [
            ("sensor.existing_power", 0, {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}),
            ("sensor.existing_energy", 10, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR}),
        ],
    )
    await run_powercalc_setup(
        hass,
        {
            CONF_POWER_SENSOR_ID: "sensor.existing_power",
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )


async def test_tariff_sensors_are_created(hass: HomeAssistant) -> None:
    await set_states(hass, [("input_boolean.test", STATE_OFF)])

    assert await async_setup_component(hass, utility_meter.DOMAIN, {})

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

    assert_entity_state(hass, "select.test_energy_daily", "peak")

    assert_entity_state(
        hass,
        "sensor.test_energy_daily_peak",
        attributes={ATTR_TARIFF: "peak", ATTR_STATUS: COLLECTING},
    )

    assert_entity_state(
        hass,
        "sensor.test_energy_daily_offpeak",
        attributes={ATTR_TARIFF: "offpeak", ATTR_STATUS: PAUSED},
    )

    general_sensor_daily = hass.states.get("sensor.test_energy_daily")
    assert general_sensor_daily

    general_sensor_hourly = hass.states.get("sensor.test_energy_hourly")
    assert general_sensor_hourly

    assert_entity_state(hass, "select.test_energy_daily", "peak")

    await set_states(hass, [("select.test_energy_daily", "offpeak")])
    assert_entity_state(hass, "sensor.test_energy_daily_peak", attributes={ATTR_STATUS: PAUSED})

    assert_entity_state(hass, "sensor.test_energy_daily_offpeak", attributes={ATTR_STATUS: COLLECTING})


async def test_tariff_meter_tracks_existing_energy_sensor(hass: HomeAssistant) -> None:
    await setup_existing_energy_tariff_meters(hass)

    assert_entity_state(hass, "select.existing_energy_daily", "peak")
    await set_states(
        hass,
        [("sensor.existing_energy", 12, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})],
    )

    assert_entity_state(
        hass,
        "sensor.existing_energy_daily_peak",
        "2.0000",
        attributes={ATTR_STATUS: COLLECTING},
    )
    assert_entity_state(
        hass,
        "sensor.existing_energy_daily_offpeak",
        "0",
        attributes={ATTR_STATUS: PAUSED},
    )


async def test_tariff_meter_recovers_when_select_becomes_available(hass: HomeAssistant) -> None:
    with (
        patch.object(TariffSelect, "current_option", new_callable=PropertyMock, return_value=None),
        patch("homeassistant.components.utility_meter.sensor.async_at_started", return_value=lambda: None),
    ):
        await setup_existing_energy_tariff_meters(hass)

    assert_entity_state(hass, "select.existing_energy_daily", "unknown")
    await set_states(hass, [("select.existing_energy_daily", "peak")])
    await set_states(
        hass,
        [("sensor.existing_energy", 12, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})],
    )

    assert_entity_state(
        hass,
        "sensor.existing_energy_daily_peak",
        "2.0000",
        attributes={ATTR_STATUS: COLLECTING},
    )
    assert_entity_state(
        hass,
        "sensor.existing_energy_daily_offpeak",
        "0",
        attributes={ATTR_STATUS: PAUSED},
    )

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.existing_energy_daily", "option": "offpeak"},
        blocking=True,
    )
    await set_states(
        hass,
        [("sensor.existing_energy", 15, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})],
    )

    assert_entity_state(
        hass,
        "sensor.existing_energy_daily_peak",
        "2.0000",
        attributes={ATTR_STATUS: PAUSED},
    )
    assert_entity_state(
        hass,
        "sensor.existing_energy_daily_offpeak",
        "3.0000",
        attributes={ATTR_STATUS: COLLECTING},
    )


async def test_tariff_sensors_created_for_gui_sensors(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    entry1 = await create_mock_config_entry(
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

    entry2 = await create_mock_config_entry(
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

    assert_entity_state(hass, "select.test_energy_daily", "peak")

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
    entity_registry = mock_entities_in_registry(
        hass,
        {
            power_sensor_id: {"name": "Test power", "platform": "powercalc"},
            energy_sensor_id: {"unique_id": "1234_energy", "name": "Test energy", "platform": "powercalc"},
            utility_meter_id: {"unique_id": "1234_energy_daily", "name": "Test energy daily", "platform": "powercalc"},
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

    await set_states(hass, [("sensor.test_energy", 1, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})])
    now = dt_util.utcnow() + timedelta(seconds=10)
    with freeze_time(now):
        await set_states(
            hass,
            [
                (
                    "sensor.test_energy",
                    3,
                    {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
                    True,
                ),
            ],
        )
    registry_entry = entity_registry.async_get("sensor.test_energy_daily")
    assert registry_entry
    assert registry_entry.options == {"sensor": {"suggested_display_precision": 2}}

    assert_entity_state(
        hass,
        "sensor.test_energy_daily",
        "2.00",
        attributes={ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )


async def test_utility_meters_not_duplicated_for_shared_energy_sensor(hass: HomeAssistant) -> None:
    """Two power sensors on one device resolve to the same related energy sensor.

    Only one set of utility meters must be created for it, not one set per configured sensor.
    See https://github.com/bramstroker/homeassistant-powercalc/issues/1799
    """
    power_sensor_id = "sensor.test_power"
    power_sensor2_id = "sensor.test2_power"
    energy_sensor_id = "sensor.test_energy"
    device_id = "some_device"
    mock_entities_in_registry(
        hass,
        {
            power_sensor_id: {
                "unique_id": "29742725-6F34-49F2-91DE-589951306E9F",
                "name": "Test power",
                "platform": "sensor",
                "device_id": device_id,
            },
            power_sensor2_id: {
                "unique_id": "A1CBB81F-A958-482B-A10E-1DAA0652796A",
                "name": "Test power2",
                "platform": "sensor",
                "device_id": device_id,
            },
            energy_sensor_id: {
                "unique_id": "4FA9B62F-E957-4366-B7DA-832C1D5F742D",
                "name": "Test energy",
                "platform": "sensor",
                "device_id": device_id,
                "device_class": SensorDeviceClass.ENERGY,
            },
        },
    )

    mock_device(hass, device_id, "foo", "bar")

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

    assert sorted(hass.states.async_entity_ids("sensor")) == [
        "sensor.all_standby_energy",
        "sensor.all_standby_energy_daily",
        "sensor.all_standby_energy_monthly",
        "sensor.all_standby_energy_weekly",
        "sensor.all_standby_power",
        "sensor.test_energy_daily",
        "sensor.test_energy_monthly",
        "sensor.test_energy_weekly",
    ]


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


async def test_entity_id_is_slugified(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test that the entity_id is slugified."""

    caplog.set_level(logging.WARNING)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.my_switch",
            CONF_UNIQUE_ID: "1234",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_UTILITY_METERS: True,
        },
        {
            CONF_UTILITY_METER_TYPES: [DAILY, QUARTER_HOURLY],
        },
    )

    assert hass.states.get("sensor.my_switch_energy_daily")
    assert hass.states.get("sensor.my_switch_energy_quarter_hourly")

    assert "Detected that custom integration 'powercalc' sets an invalid entity ID" not in caplog.text
