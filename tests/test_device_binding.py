import logging

from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_SENSOR_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryDisabler, DeviceRegistry
import homeassistant.helpers.entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
)

from custom_components.powercalc import device_binding
from custom_components.powercalc.common import SourceEntity, create_source_entity, get_main_device_entry
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
from custom_components.powercalc.device_binding import (
    get_config_entry_ids,
    get_first_device_for_config_entry,
    get_non_composite_devices,
    get_related_device_ids,
    is_composite_device_id,
    resolve_source_device,
)
from tests.common import (
    create_mock_config_entry,
    mock_device,
    mock_device_with_entities,
    mock_devices,
    mock_entities_in_registry,
    requires_child_devices,
    run_powercalc_setup,
)


def test_regular_device_is_not_composite(
    hass: HomeAssistant,
) -> None:
    """A regular device ID is not treated as a legacy composite device."""
    device_entry = mock_device(hass, "regular-device", manufacturer=None, model=None)

    assert not is_composite_device_id(hass, device_entry.id)


def test_device_is_not_composite_when_detection_is_unavailable(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A device is not composite on HA versions without the detection API."""
    device_entry = mock_device(hass, "regular-device", manufacturer=None, model=None)
    monkeypatch.setattr(device_binding, "_HAS_CHILD_DEVICES", False)
    monkeypatch.setattr(DeviceRegistry, "async_is_composite_device_id", None, raising=False)

    assert not is_composite_device_id(hass, device_entry.id)


def test_get_non_composite_devices_enumerates_registered_devices(hass: HomeAssistant) -> None:
    device_entry = mock_device(hass, "regular-device", manufacturer=None, model=None)

    assert get_non_composite_devices(hass) == [device_entry]


def test_get_related_device_ids_for_unknown_device(hass: HomeAssistant) -> None:
    mock_device_registry(hass)

    assert get_related_device_ids(hass, "missing-device") == {"missing-device"}


def test_get_first_device_for_config_entry(hass: HomeAssistant) -> None:
    device_entry = mock_device(hass, "regular-device", manufacturer=None, model=None)

    config_entry_id = next(iter(get_config_entry_ids(device_entry)))

    assert get_first_device_for_config_entry(hass, config_entry_id) == device_entry


@requires_child_devices
def test_get_main_device_entry_excludes_child_devices(
    hass: HomeAssistant,
    device_registry: DeviceRegistry,
) -> None:
    """Child devices are not returned to code which requires a full device entry."""
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    parent = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("test", "parent")},
        name="Parent",
    )
    child = device_registry.async_get_or_create_child(
        config_entry_id=config_entry.entry_id,
        identifiers={("test", "child")},
        name="Child",
        parent_device_id=parent.id,
    )

    assert get_main_device_entry(device_registry, parent.id) == parent
    assert get_main_device_entry(device_registry, child.id) is None


@requires_child_devices
async def test_entities_are_bound_to_child_source_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: DeviceRegistry,
) -> None:
    """Child association is retained without reading main-device-only fields."""
    source_config_entry = MockConfigEntry(domain="test")
    source_config_entry.add_to_hass(hass)
    parent = device_registry.async_get_or_create(
        config_entry_id=source_config_entry.entry_id,
        identifiers={("test", "parent")},
        name="Parent",
    )
    child = device_registry.async_get_or_create_child(
        config_entry_id=source_config_entry.entry_id,
        identifiers={("test", "child")},
        name="Child",
        parent_device_id=parent.id,
    )
    entity_registry.async_get_or_create(
        "switch",
        "test",
        "child-source",
        suggested_object_id="child_source",
        device_id=child.id,
    )

    source_entity = create_source_entity("switch.child_source", hass)
    assert source_entity.device_entry == child
    assert get_related_device_ids(hass, child.id) == {child.id}

    configured_source = resolve_source_device(
        hass,
        {CONF_DEVICE: child.id},
        SourceEntity(object_id="configured", entity_id=DUMMY_ENTITY_ID, domain="sensor"),
    )
    assert configured_source.device_entry == child

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.child_source",
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    power_entity_entry = entity_registry.async_get("sensor.child_source_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == child.id


def test_resolve_source_device_keeps_source_entity_when_device_is_missing(hass: HomeAssistant) -> None:
    mock_device_registry(hass)
    source_entity = SourceEntity(object_id="powercalc_dummy", entity_id=DUMMY_ENTITY_ID, domain="sensor")

    result = resolve_source_device(hass, {CONF_DEVICE: "missing-device-id"}, source_entity)

    assert result == source_entity


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


async def test_entities_are_bound_to_source_device_when_using_power_sensor_id(
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

    entity_reg = mock_entities_in_registry(
        hass,
        {
            switch_id: {"platform": "switch", "device_id": device_id},
            power_sensor_id: {"platform": "sensor", "device_id": device_id},
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


async def test_yaml_sensor_is_bound_to_source_device(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """YAML entities are bound with a registry update, which must not trigger the HA device attach warning."""
    caplog.set_level(logging.WARNING)

    entity_registry = mock_device_with_entities(hass, "light.test")
    await run_powercalc_setup(hass, {CONF_ENTITY_ID: "light.test"})

    power_sensor = entity_registry.async_get("sensor.test_power")
    assert power_sensor
    assert power_sensor.device_id == "model-device"

    assert "attempts to attach a device to an entity without a config entry" not in caplog.text


async def test_entities_are_bound_to_disabled_source_device(
    hass: HomeAssistant,
) -> None:
    device_id = "device.test"
    power_sensor_id = "sensor.test_power"
    light_id = "light.test"

    mock_device(hass, device_id, "signify", "LCA001", disabled_by=DeviceEntryDisabler.USER)

    entity_reg = mock_entities_in_registry(
        hass,
        {
            light_id: {"disabled_by": er.RegistryEntryDisabler.DEVICE, "platform": "light", "device_id": device_id},
            power_sensor_id: {
                "disabled_by": er.RegistryEntryDisabler.DEVICE,
                "platform": "powercalc",
                "device_id": device_id,
            },
        },
    )

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: light_id},
    )

    energy_entity_entry = entity_reg.async_get(power_sensor_id)
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_id


async def test_entities_are_bound_to_configured_device_without_source_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """A device based profile has no source entity, so the sensors bind to the configured device."""
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

    power_entity_entry = entity_registry.async_get("sensor.test_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == device_id


async def test_configured_device_takes_precedence_over_source_device(
    hass: HomeAssistant,
) -> None:
    devices = mock_devices(
        hass,
        {
            "source-device": {"manufacturer": "source", "model": "Source Device"},
            "configured-device": {"manufacturer": "configured", "model": "Configured Device"},
        },
    )
    source_device = devices["source-device"]
    configured_device = devices["configured-device"]

    entity_registry = mock_entities_in_registry(
        hass,
        {
            "switch.configured_precedence": {
                "unique_id": "configured-precedence-source",
                "device_id": source_device.id,
            },
        },
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.configured_precedence",
            CONF_DEVICE: configured_device.id,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    for entity_id in (
        "sensor.configured_precedence_power",
        "sensor.configured_precedence_energy",
        "sensor.configured_precedence_energy_daily",
    ):
        entity_entry = entity_registry.async_get(entity_id)
        assert entity_entry
        assert entity_entry.device_id == configured_device.id
