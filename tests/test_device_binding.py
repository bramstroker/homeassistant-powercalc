import logging

from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_SENSOR_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryDisabler, DeviceRegistry
import homeassistant.helpers.entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    RegistryEntryWithDefaults,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    DUMMY_ENTITY_ID,
    SensorType,
)
from tests.common import create_mock_config_entry, mock_device, run_powercalc_setup


async def test_entities_are_bound_to_source_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: DeviceRegistry,
) -> None:
    """
    Test that all powercalc created sensors are attached to same device as the source entity
    """

    # Create a device
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("dummy", "abcdef")},
        manufacturer="Google Inc.",
        model="Google Home Mini",
    )

    # Create a source entity which is bound to the device
    unique_id = "34445329342797234"
    entity_registry.async_get_or_create(
        "switch",
        "switch",
        unique_id,
        suggested_object_id="google_home",
        device_id=device_entry.id,
    )

    # Create powercalc sensors
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.google_home",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    # Assert that all the entities are bound to correct device
    power_entity_entry = entity_registry.async_get("sensor.google_home_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == device_entry.id

    energy_entity_entry = entity_registry.async_get("sensor.google_home_energy")
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_entry.id

    utility_entity_entry = entity_registry.async_get("sensor.google_home_energy_daily")
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

    mock_device(hass, device_id, "shelly", "Plug S")

    entity_reg = mock_registry(
        hass,
        {
            switch_id: RegistryEntryWithDefaults(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id=device_id,
            ),
            power_sensor_id: RegistryEntryWithDefaults(
                entity_id=power_sensor_id,
                unique_id="12345",
                platform="sensor",
                device_id=device_id,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "switch.shelly", CONF_POWER_SENSOR_ID: "sensor.shelly_power"},
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

    mock_device(hass, device_id, "signify", "LCA001", disabled_by=DeviceEntryDisabler.USER)

    entity_reg = mock_registry(
        hass,
        {
            light_id: RegistryEntryWithDefaults(
                entity_id=light_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="light",
                device_id=device_id,
            ),
            power_sensor_id: RegistryEntryWithDefaults(
                entity_id=power_sensor_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="powercalc",
                device_id=device_id,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: light_id},
    )

    energy_entity_entry = entity_reg.async_get(power_sensor_id)
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_id


async def test_entities_are_bound_to_source_device3(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    device_id = "abc"
    mock_device(hass, device_id, "test", "test")

    await create_mock_config_entry(
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
    await run_powercalc_setup(hass)

    power_entity_entry = entity_registry.async_get("sensor.test_device_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == device_id


async def test_powercalc_config_entry_is_removed_from_device_on_setup(hass: HomeAssistant) -> None:
    device_registry = mock_device_registry(hass, {})
    device_owner_config_entry = MockConfigEntry(domain="test")
    device_owner_config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=device_owner_config_entry.entry_id,
        identifiers={("shelly", "PlugS")},
        manufacturer="shelly",
        model="PlugS",
    )

    entry_data = {
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_NAME: "Test",
        CONF_ENTITY_ID: DUMMY_ENTITY_ID,
        CONF_FIXED: {CONF_POWER: 50},
    }
    config_entry = await create_mock_config_entry(
        hass,
        {
            **entry_data,
            CONF_DEVICE: device_entry.id,
        },
        setup=False,
    )
    device_registry.async_update_device(device_entry.id, add_config_entry_id=config_entry.entry_id)

    device1 = device_registry.async_get(device_entry.id)
    assert device1
    assert config_entry.entry_id in device1.config_entries

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device1 = device_registry.async_get(device_entry.id)
    assert device1
    assert config_entry.entry_id not in device1.config_entries
