import logging

import homeassistant.helpers.entity_registry as er
import pytest
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_SENSOR_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry, DeviceEntryDisabler, DeviceRegistry
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_device_registry, mock_registry

from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SensorType,
)
from tests.common import get_test_config_dir, run_powercalc_setup, setup_config_entry
from tests.config_flow.common import create_mock_entry


async def test_entities_are_bound_to_source_device(
    hass: HomeAssistant,
    entity_reg: er.EntityRegistry,
    device_reg: DeviceRegistry,
) -> None:
    """
    Test that all powercalc created sensors are attached to same device as the source entity
    """

    # Create a device
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("dummy", "abcdef")},
        manufacturer="Google Inc.",
        model="Google Home Mini",
    )

    # Create a source entity which is bound to the device
    unique_id = "34445329342797234"
    entity_reg.async_get_or_create(
        "switch",
        "switch",
        unique_id,
        suggested_object_id="google_home",
        device_id=device_entry.id,
    )
    await hass.async_block_till_done()

    # Create powercalc sensors
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.google_home",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert that all the entities are bound to correct device
    power_entity_entry = entity_reg.async_get("sensor.google_home_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == device_entry.id

    energy_entity_entry = entity_reg.async_get("sensor.google_home_energy")
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_entry.id

    utility_entity_entry = entity_reg.async_get("sensor.google_home_energy_daily")
    assert utility_entity_entry
    assert utility_entity_entry.device_id == device_entry.id


async def test_entities_are_bound_to_source_device2(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    When using the power_sensor_id option the energy sensors and utility meters must be bound to the same device.
    Also make sure no errors are logged
    """

    caplog.set_level(logging.ERROR)

    device_id = "device.test"
    switch_id = "switch.shelly"
    power_sensor_id = "sensor.shelly_power"

    mock_device_registry(
        hass,
        {device_id: DeviceEntry(id=device_id, manufacturer="shelly", model="Plug S")},
    )

    entity_reg = mock_registry(
        hass,
        {
            switch_id: er.RegistryEntry(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id=device_id,
            ),
            power_sensor_id: er.RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="12345",
                platform="sensor",
                device_id=device_id,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "switch.shelly", CONF_POWER_SENSOR_ID: "sensor.shelly_power"},
        {},
    )

    energy_entity_entry = entity_reg.async_get("sensor.shelly_energy")
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_id

    assert len(caplog.records) == 0


async def test_entities_are_bound_to_disabled_source_device(
    hass: HomeAssistant,
) -> None:
    device_id = "device.test"
    power_sensor_id = "sensor.test_power"
    light_id = "light.test"

    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="signify",
                model="LCA001",
                disabled_by=DeviceEntryDisabler.USER,
            ),
        },
    )

    entity_reg = mock_registry(
        hass,
        {
            light_id: er.RegistryEntry(
                entity_id=light_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="light",
                device_id=device_id,
            ),
            power_sensor_id: er.RegistryEntry(
                entity_id=power_sensor_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="powercalc",
                device_id=device_id,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: light_id},
        {},
    )

    energy_entity_entry = entity_reg.async_get(power_sensor_id)
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_id


async def test_entities_are_bound_to_source_device3(
    hass: HomeAssistant,
    entity_reg: er.EntityRegistry,
) -> None:
    hass.config.config_dir = get_test_config_dir()

    device_id = "abc"
    mock_device_registry(
        hass,
        {device_id: DeviceEntry(id=device_id, manufacturer="test", model="test")},
    )

    create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "discovery_type_device",
            CONF_DEVICE: device_id,
        },
    )
    await run_powercalc_setup(hass, {})

    power_entity_entry = entity_reg.async_get("sensor.test_device_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == device_id


async def test_change_device(hass: HomeAssistant) -> None:
    """
    Test that changing the device in the configuration updates the device registry
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/3123
    """
    device_registry = mock_device_registry(
        hass,
        {
            "device1": DeviceEntry(
                id="device1",
                manufacturer="shelly",
                model="PlugS",
            ),
            "device2": DeviceEntry(
                id="device2",
                manufacturer="shelly",
                model="PlugS",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "entity1": er.RegistryEntry(
                entity_id="sensor.entity1",
                unique_id="1111",
                platform="shelly",
                device_id="device1",
            ),
            "entity2": er.RegistryEntry(
                entity_id="sensor.entity2",
                unique_id="2222",
                platform="shelly",
                device_id="device2",
            ),
        },
    )

    entry_data = {
        CONF_SENSOR_TYPE: SensorType.REAL_POWER,
        CONF_NAME: "Test",
        CONF_ENTITY_ID: "sensor.entity1",
    }
    config_entry = await setup_config_entry(
        hass,
        {
            **entry_data,
            CONF_DEVICE: "device1",
        },
    )

    device1 = device_registry.async_get("device1")
    assert device1.config_entries == {config_entry.entry_id}

    hass.config_entries.async_update_entry(config_entry, data={**entry_data, CONF_DEVICE: "device2"})
    await hass.async_block_till_done()

    device1 = device_registry.async_get("device1")
    assert not device1

    device2 = device_registry.async_get("device2")
    assert device2.config_entries == {config_entry.entry_id}
