import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_GROUP,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    DOMAIN,
    SERVICE_CALIBRATE_ENERGY,
    UnitPrefix,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from tests.common import (
    create_input_boolean,
    get_simple_fixed_config,
    run_powercalc_setup,
)


async def test_related_energy_sensor_is_used_for_existing_power_sensor(
    hass: HomeAssistant,
) -> None:
    await create_input_boolean(hass)

    mock_device_registry(
        hass,
        {
            "shelly-device": DeviceEntry(
                id="shelly-device-id",
                manufacturer="Shelly",
                model="Plug S",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "sensor.existing_power": RegistryEntry(
                entity_id="sensor.existing_power",
                unique_id="1234",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.existing_energy": RegistryEntry(
                entity_id="sensor.existing_energy",
                unique_id="12345",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_POWER_SENSOR_ID: "sensor.existing_power",
                },
            ],
        },
    )

    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state
    assert power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
    }

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_energy",
    }


async def test_force_create_energy_sensor_for_existing_power_sensor(
    hass: HomeAssistant,
) -> None:
    """
    When the user uses `power_sensor_id` option and a related energy sensor already exists in the system,
    creation can be forced with `force_energy_sensor_creation`
    """
    await create_input_boolean(hass)

    mock_device_registry(
        hass,
        {
            "shelly-device": DeviceEntry(
                id="shelly-device-id",
                manufacturer="Shelly",
                model="Plug S",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "sensor.existing_power": RegistryEntry(
                entity_id="sensor.existing_power",
                unique_id="1234",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.existing_energy": RegistryEntry(
                entity_id="sensor.existing_energy",
                unique_id="12345",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_NAME: "MySensor",
                    CONF_POWER_SENSOR_ID: "sensor.existing_power",
                    CONF_FORCE_ENERGY_SENSOR_CREATION: True,
                },
            ],
        },
    )

    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state
    assert power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
    }

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.mysensor_energy",
    }


async def test_disable_extended_attributes(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        {CONF_DISABLE_EXTENDED_ATTRIBUTES: True},
    )

    energy_state = hass.states.get("sensor.test_energy")
    assert ATTR_SOURCE_DOMAIN not in energy_state.attributes
    assert ATTR_SOURCE_ENTITY not in energy_state.attributes


async def test_real_energy_sensor(hass: HomeAssistant) -> None:
    """Test user can refer an existing real energy sensor to create utility meters for it or add to group with YAML"""

    mock_registry(
        hass,
        {
            "sensor.existing_energy": RegistryEntry(
                entity_id="sensor.existing_energy",
                unique_id="12345",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_FIXED: {CONF_POWER: 50},
                    CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
                },
            ],
        },
    )

    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_energy",
    }


async def test_real_energy_sensor_error_on_non_existing_entity(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that an error is logged when user supplies unknown entity id in energy_sensor_id"""

    caplog.set_level(logging.ERROR)

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_FIXED: {CONF_POWER: 50},
                    CONF_ENERGY_SENSOR_ID: "sensor.invalid_energy",
                },
            ],
        },
    )

    await hass.async_block_till_done()

    assert "No energy sensor with id" in caplog.text


async def test_unit_prefix_none(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        {CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE},
    )

    async_fire_time_changed(
        hass,
        dt.utcnow() + timedelta(hours=1),
    )

    hass.states.async_set("sensor.test_power", "50.00")

    await hass.async_block_till_done()

    state_attributes = hass.states.get("sensor.test_energy").attributes
    assert state_attributes.get("unit_of_measurement") == UnitOfEnergy.WATT_HOUR


async def test_unit_prefix_kwh_default(hass: HomeAssistant) -> None:
    """By default, unit prefix should be k, resulting in kWh energy sensor created for a W power sensor"""
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
    )

    async_fire_time_changed(
        hass,
        dt.utcnow() + timedelta(hours=1),
    )

    hass.states.async_set("sensor.test_power", "50.00")

    await hass.async_block_till_done()

    state_attributes = hass.states.get("sensor.test_energy").attributes
    assert state_attributes.get("unit_of_measurement") == UnitOfEnergy.KILO_WATT_HOUR


async def test_set_entity_category(hass: HomeAssistant) -> None:
    energy_sensor = VirtualEnergySensor(
        source_entity="sensor.test_power",
        entity_id="sensor.test_energy",
        name="Test energy",
        round_digits=2,
        unit_prefix="k",
        unit_time=UnitOfTime(UnitOfTime.HOURS),
        unique_id="1234",
        entity_category=EntityCategory(EntityCategory.DIAGNOSTIC),
        integration_method="",
        powercalc_source_entity="light.test",
        powercalc_source_domain="light",
        sensor_config={},
    )
    assert energy_sensor.entity_category == EntityCategory.DIAGNOSTIC


async def test_calibrate_service(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
    )
    entity_id = "sensor.test_energy"

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


async def test_real_power_sensor_kw(hass: HomeAssistant) -> None:
    """
    Test that the riemann integral sensor is correclty created and updated for a kW power sensor
    Fixes https://github.com/bramstroker/homeassistant-powercalc/issues/1676
    """

    hass.states.async_set(
        "sensor.test_power",
        "100",
        {
            ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            ATTR_DEVICE_CLASS: SensorDeviceClass.POWER,
            ATTR_STATE_CLASS: SensorStateClass.MEASUREMENT,
        },
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_UNIQUE_ID: "1234353",
            CONF_POWER_SENSOR_ID: "sensor.test_power",
        },
    )

    state = hass.states.get("sensor.test_energy")
    assert state

    now = dt.utcnow() + timedelta(minutes=60)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        hass.states.async_set(
            "sensor.test_power",
            "200",
            {
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
                ATTR_DEVICE_CLASS: SensorDeviceClass.POWER,
                ATTR_STATE_CLASS: SensorStateClass.MEASUREMENT,
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.test_energy")
    assert state
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.KILO_WATT_HOUR
