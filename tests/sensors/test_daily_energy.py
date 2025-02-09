from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ON_TIME,
    CONF_SENSOR_TYPE,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    DOMAIN,
    SERVICE_CALIBRATE_ENERGY,
    SERVICE_INCREASE_DAILY_ENERGY,
    SERVICE_RESET_ENERGY,
    SensorType,
    UnitPrefix,
)
from custom_components.powercalc.sensors.daily_energy import (
    DEFAULT_DAILY_UPDATE_FREQUENCY,
    create_daily_fixed_energy_sensor,
)
from tests.common import (
    assert_entity_state,
    create_input_boolean,
    create_input_number,
    run_powercalc_setup,
)


async def test_create_daily_energy_sensor_default_options(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_DAILY_FIXED_ENERGY: {},
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)
    assert sensor
    assert sensor.name == "My sensor Energy"
    assert sensor.entity_id == "sensor.my_sensor_energy"
    assert sensor.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert sensor.device_class == SensorDeviceClass.ENERGY
    assert sensor.state_class == SensorStateClass.TOTAL


@pytest.mark.parametrize(
    "unit_prefix,unit_of_measurement",
    [
        (UnitPrefix.NONE, UnitOfEnergy.WATT_HOUR),
        (UnitPrefix.KILO, UnitOfEnergy.KILO_WATT_HOUR),
        (UnitPrefix.MEGA, UnitOfEnergy.MEGA_WATT_HOUR),
    ],
)
async def test_create_daily_energy_sensor_unit_prefix_watt(
    hass: HomeAssistant,
    unit_prefix: str,
    unit_of_measurement: str,
) -> None:
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
    assert sensor.native_unit_of_measurement == unit_of_measurement


async def test_daily_energy_sensor_from_kwh_value(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 12,
            },
        },
    )

    sensor_entity_id = "sensor.ip_camera_upstairs_energy"
    state = hass.states.get(sensor_entity_id)
    assert state
    assert state.attributes.get("state_class") == SensorStateClass.TOTAL
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.KILO_WATT_HOUR

    await _trigger_periodic_update(hass)
    assert_entity_state(hass, sensor_entity_id, "0.2500")

    await _trigger_periodic_update(hass)
    assert_entity_state(hass, sensor_entity_id, "0.5000")

    await _trigger_periodic_update(hass, 2)
    assert_entity_state(hass, sensor_entity_id, "1.0000")

    # Trigger remaining updates to get a full day
    # Default update frequency is 1800 seconds (half an hour)
    # So 48 - 4 = 44 updates makes for a full day
    await _trigger_periodic_update(hass, 44)
    assert_entity_state(hass, sensor_entity_id, "12.0000")


async def test_utility_meters_are_created(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 12,
            },
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    assert hass.states.get("sensor.ip_camera_upstairs_energy_daily")


async def test_daily_energy_sensor_also_creates_power_sensor(
    hass: HomeAssistant,
) -> None:
    """
    When the user configured the value in W and the on_time is always on,
    then a power sensor should also be created
    """
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 15,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
        },
    )

    state = hass.states.get("sensor.ip_camera_upstairs_energy")
    assert state
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.KILO_WATT_HOUR

    state = hass.states.get("sensor.ip_camera_upstairs_power")
    assert state
    assert state.state == "15.00"
    assert state.name == "IP camera upstairs power"


async def test_daily_energy_sensor_kwh_also_creates_power_sensor(
    hass: HomeAssistant,
) -> None:
    """
    When the user configured the value in kWh and the on_time is always on,
    then a power sensor should also be created
    """
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Heater",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 12,
                CONF_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
            },
        },
    )

    state = hass.states.get("sensor.heater_power")
    assert state
    assert state.state == "500.00"
    assert state.name == "Heater power"


async def test_power_sensor_not_created_when_not_on_whole_day(
    hass: HomeAssistant,
) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 15,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                CONF_ON_TIME: timedelta(hours=4),
            },
        },
    )

    assert hass.states.get("sensor.ip_camera_upstairs_energy")
    assert not hass.states.get("sensor.ip_camera_upstairs_power")


@pytest.mark.parametrize(
    "daily_fixed_options,elapsed_seconds,expected_delta",
    [
        (
            {
                CONF_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
                CONF_ON_TIME: timedelta(days=1),
                CONF_VALUE: 12,
            },
            3600,
            0.5,
        ),
        (
            # Consume 1500 x 2 hour = 3 kWh a day
            {
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                CONF_ON_TIME: timedelta(hours=2),
                CONF_VALUE: 2000,
            },
            1200,  # Simulate 20 minutes
            0.0555,
        ),
        (
            {
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                CONF_ON_TIME: 3600,  # Test that on time can be passed as seconds
                CONF_VALUE: 2400,
            },
            1800,  # Simulate 30 minutes
            0.05,
        ),
    ],
)
async def test_calculate_delta(
    hass: HomeAssistant,
    daily_fixed_options: ConfigType,
    elapsed_seconds: int,
    expected_delta: float,
) -> None:
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_DAILY_FIXED_ENERGY: daily_fixed_options,
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)

    delta = sensor.calculate_delta(elapsed_seconds)
    assert expected_delta == pytest.approx(float(delta), 0.001)


async def test_calculate_delta_mega_watt_hour(hass: HomeAssistant) -> None:
    sensor_config = {
        CONF_ENERGY_SENSOR_NAMING: "{} Energy",
        CONF_NAME: "My sensor",
        CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.MEGA,
        CONF_DAILY_FIXED_ENERGY: {
            CONF_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
            CONF_ON_TIME: timedelta(days=1),
            CONF_VALUE: 12,
        },
    }
    sensor = await create_daily_fixed_energy_sensor(hass, sensor_config)

    # Calculate delta after 1 hour
    delta = sensor.calculate_delta(3600)
    assert pytest.approx(float(delta), 0.001) == 0.0005


async def test_template_value(hass: HomeAssistant) -> None:
    await create_input_number(hass, "test", 50)

    update_frequency = 1800
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Router",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: "{{states('input_number.test')}}",
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                CONF_UPDATE_FREQUENCY: update_frequency,
            },
        },
    )

    # Trigger calculation in the future
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=43200))
    await hass.async_block_till_done()

    state = hass.states.get("sensor.router_energy")
    assert state.state == "0.0250"


async def test_config_flow_template_value(hass: HomeAssistant) -> None:
    """
    Test that power sensor is correctly created when a template is used as the value
    See https://github.com/bramstroker/homeassistant-powercalc/issues/980
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "My daily",
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_DAILY_FIXED_ENERGY: {
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                CONF_VALUE_TEMPLATE: "{{ 5*0.5 }}",
            },
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.my_daily_power")
    assert power_state
    assert power_state.state == "2.50"


async def test_config_flow_decimal_value(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "My daily",
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_DAILY_FIXED_ENERGY: {
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                CONF_VALUE: 0.3,
            },
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.my_daily_power")
    assert power_state
    assert power_state.state == "0.30"


async def test_reset_service(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "IP camera upstairs",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 15,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
        },
    )

    entity_id = "sensor.ip_camera_upstairs_energy"

    # Set the individual entities to some initial values
    hass.states.async_set(
        entity_id,
        "0.8",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "0.8"

    # Reset the group sensor and underlying group members
    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESET_ENERGY,
        {
            ATTR_ENTITY_ID: entity_id,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "0.0000"


async def test_increase_service(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Dishwasher",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 0,
            },
        },
    )

    entity_id = "sensor.dishwasher_energy"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_INCREASE_DAILY_ENERGY,
        {ATTR_ENTITY_ID: entity_id, "value": 1.2},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "1.2000"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_INCREASE_DAILY_ENERGY,
        {ATTR_ENTITY_ID: entity_id, "value": 1.5},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "2.7000"


async def test_calibrate_service(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Dishwasher",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 0,
            },
        },
    )
    entity_id = "sensor.dishwasher_energy"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_ENERGY,
        {
            ATTR_ENTITY_ID: entity_id,
            "value": "100",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "100.0000"


async def test_restore_state(hass: HomeAssistant) -> None:
    mock_restore_cache(
        hass,
        [
            State(
                "sensor.my_daily_energy",
                "0.5",
            ),
        ],
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "My daily",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 1.5,
            },
        },
    )

    assert hass.states.get("sensor.my_daily_energy").state == "0.5000"


async def test_restore_state_catches_decimal_conversion_exception(
    hass: HomeAssistant,
) -> None:
    mock_restore_cache(
        hass,
        [
            State(
                "sensor.my_daily_energy",
                "unknown",
            ),
        ],
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "My daily",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 1.5,
            },
        },
    )

    assert hass.states.get("sensor.my_daily_energy").state == "0.0000"


async def test_small_update_frequency_updates_correctly(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Router",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_UPDATE_FREQUENCY: 60,  # Update each minute
                CONF_VALUE: 0.24,
            },
        },
    )

    await _trigger_periodic_update(hass, 10)
    assert_entity_state(hass, "sensor.router_energy", "0.0017")

    await _trigger_periodic_update(hass, 50)
    assert_entity_state(hass, "sensor.router_energy", "0.0100")


async def test_name_and_entity_id_can_be_inherited_from_source_entity(
    hass: HomeAssistant,
) -> None:
    await create_input_boolean(hass, "test")
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_VALUE: 0.24,
            },
        },
    )
    state = hass.states.get("sensor.test_energy")
    assert state


async def test_create_daily_energy_sensor_using_config_entry(
    hass: HomeAssistant,
) -> None:
    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_NAME: "Test",
            CONF_DAILY_FIXED_ENERGY: {
                CONF_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
                CONF_VALUE: 200,
                CONF_UPDATE_FREQUENCY: 1800.0,
            },
            CONF_CREATE_UTILITY_METERS: True,
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy")

    assert hass.states.get("sensor.test_energy_daily")


async def test_template_error_catched(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    with patch("homeassistant.helpers.template.Template.async_render", side_effect=TemplateError(Exception())):
        await run_powercalc_setup(
            hass,
            {
                CONF_ENERGY_SENSOR_NAMING: "{} Energy",
                CONF_NAME: "My sensor",
                CONF_DAILY_FIXED_ENERGY: {
                    CONF_VALUE: "{{ 1 + 3 }}",
                },
            },
        )
        await _trigger_periodic_update(hass, 10)
        assert "Could not render value template" in caplog.text


async def _trigger_periodic_update(
    hass: HomeAssistant,
    number_of_updates: int = 1,
) -> None:
    for _i in range(number_of_updates):
        async_fire_time_changed(
            hass,
            dt.utcnow() + timedelta(seconds=DEFAULT_DAILY_UPDATE_FREQUENCY),
        )
        await hass.async_block_till_done()
