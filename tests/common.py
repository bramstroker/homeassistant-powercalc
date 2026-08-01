from collections.abc import Mapping
from datetime import timedelta
import os
from typing import Any
import uuid

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.helpers.typing import ConfigType, StateType
from homeassistant.setup import async_setup_component
from homeassistant.util import dt
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    RegistryEntryWithDefaults,
    async_fire_time_changed,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import (
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_POWER_UPDATE_INTERVAL,
    async_migrate_entry,
)
from custom_components.powercalc.config_flow import PowercalcConfigFlow
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_SENSORS,
    DOMAIN,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)

type StateDefinition = (
    tuple[str, StateType] | tuple[str, StateType, Mapping[str, Any]] | tuple[str, StateType, Mapping[str, Any], bool]
)

_HAS_SINGLE_CONFIG_ENTRY = hasattr(DeviceEntry, "config_entry_id")

requires_composite_devices = pytest.mark.skipif(
    not hasattr(DeviceEntry, "composite_device_id"),
    reason="Composite devices were only split off in HA >=2026.8",
)


async def run_powercalc_setup(
    hass: HomeAssistant,
    sensor_config: list[ConfigType] | ConfigType | None = None,
    domain_config: ConfigType | None = None,
) -> None:
    domain_config = {
        CONF_ENERGY_UPDATE_INTERVAL: 0,
        CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
        CONF_GROUP_POWER_UPDATE_INTERVAL: 0,
        **(domain_config or {}),
    }

    config = {DOMAIN: domain_config or {}}

    if not sensor_config:
        sensor_config = {}
    if sensor_config and not isinstance(sensor_config, list):
        sensor_config = [sensor_config]

    if sensor_config:
        config[DOMAIN][CONF_SENSORS] = sensor_config

    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()


def get_simple_fixed_config(entity_id: str, power: float = 50) -> ConfigType:
    return {
        CONF_ENTITY_ID: entity_id,
        CONF_MODE: CalculationStrategy.FIXED,
        CONF_FIXED: {CONF_POWER: power},
    }


def get_test_profile_dir(sub_dir: str) -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "testing_config/powercalc/profiles/test",
        sub_dir,
    )


def get_test_config_dir(append_path: str = "") -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "testing_config",
        append_path,
    )


async def create_mock_config_entry(
    hass: HomeAssistant,
    entry_data: dict,
    unique_id: str | None = None,
    title: str | None = None,
    source: str = config_entries.SOURCE_USER,
    setup: bool = True,
) -> MockConfigEntry:
    """Add a Powercalc config entry, optionally running its setup."""
    if unique_id is None:
        unique_id = str(uuid.uuid4())
    if title is None:
        title = entry_data.get(CONF_NAME, "Mock Title")

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data,
        unique_id=unique_id,
        title=title,
        source=source,
    )
    config_entry.add_to_hass(hass)
    if setup:
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


async def create_mock_group_entry(
    hass: HomeAssistant,
    name: str,
    entry_data: dict | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> MockConfigEntry:
    """Add a Powercalc group config entry named `name`."""
    return await create_mock_config_entry(
        hass,
        {CONF_SENSOR_TYPE: SensorType.GROUP, CONF_NAME: name, **(entry_data or {})},
        **kwargs,
    )


def build_device_entry(**kwargs: Any) -> DeviceEntry:  # noqa: ANN401
    """Build a `DeviceEntry` from HA >=2026.8 style kwargs.

    HA >=2026.8 stores a single `config_entry_id` on the device. Older versions, which Powercalc
    still supports, track a set of `config_entries` plus a `primary_config_entry` instead.
    """
    if not _HAS_SINGLE_CONFIG_ENTRY:
        config_entry_id = kwargs.pop("config_entry_id", None)
        if config_entry_id is not None:
            kwargs["config_entries"] = {config_entry_id}
            kwargs["primary_config_entry"] = config_entry_id

    return DeviceEntry(**kwargs)


def mock_devices(
    hass: HomeAssistant,
    devices: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, DeviceEntry]:
    """Register mocked devices, replacing any prior mocked registry.

    Keys are device ids, values the extra `DeviceEntry` kwargs. Entries without an explicit
    `config_entry_id` share a single mock config entry. Devices cannot be registered one by one,
    every call replaces the whole registry, so pass all of them at once.
    """
    shared_config_entry_id: str | None = None
    entries: dict[str, DeviceEntry] = {}
    for device_id, device_kwargs in devices.items():
        kwargs = dict(device_kwargs or {})
        if "config_entry_id" not in kwargs:
            if shared_config_entry_id is None:
                config_entry = MockConfigEntry(domain="test")
                config_entry.add_to_hass(hass)
                shared_config_entry_id = config_entry.entry_id
            kwargs["config_entry_id"] = shared_config_entry_id
        entries[device_id] = build_device_entry(id=device_id, **kwargs)

    mock_device_registry(hass, entries)
    return entries


def mock_device(
    hass: HomeAssistant,
    device_id: str = "test-device",
    manufacturer: str | None = "test",
    model: str | None = "test",
    **kwargs: Any,  # noqa: ANN401
) -> DeviceEntry:
    """Register a single mocked device, replacing any prior mocked registry.

    Use `mock_devices` when a test needs more than one device.
    """
    return mock_devices(hass, {device_id: {"manufacturer": manufacturer, "model": model, **kwargs}})[device_id]


def mock_entities_in_registry(
    hass: HomeAssistant,
    entities: Mapping[str, Mapping[str, Any] | None],
) -> EntityRegistry:
    """Register mocked entities, replacing any prior mocked registry.

    Keys are entity ids, values the extra `RegistryEntryWithDefaults` kwargs. `platform` defaults
    to the domain of the entity id and `unique_id` is derived from it, so a test only needs to spell
    out the fields it actually cares about.
    """
    entries = {}
    for entity_id, entity_kwargs in entities.items():
        kwargs = dict(entity_kwargs or {})
        kwargs.setdefault("platform", split_entity_id(entity_id)[0])
        kwargs.setdefault("unique_id", entity_id)
        entries[entity_id] = RegistryEntryWithDefaults(entity_id=entity_id, **kwargs)

    return mock_registry(hass, entries)


def mock_device_with_entities(
    hass: HomeAssistant,
    entity_ids: str | list[str],
    manufacturer: str = "signify",
    model: str = "LCT010",
    model_id: str | None = None,
    **entity_kwargs: Any,  # noqa: ANN401
) -> None:
    """Register entities on a single device carrying manufacturer/model info, so discovery can match a profile.

    Replaces both registries, so call it once per test and use `mock_devices` /
    `mock_entities_in_registry` directly when a test needs several devices or per-entity kwargs.
    """
    device_id = "model-device"
    mock_devices(hass, {device_id: {"manufacturer": manufacturer, "model": model, "model_id": model_id}})

    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    unique_id = entity_kwargs.pop("unique_id", None)
    mock_entities_in_registry(
        hass,
        {
            entity_id: {
                "platform": "foo",
                "device_id": device_id,
                # Keep unique ids distinct when one explicit id is shared by several entities.
                **(
                    {"unique_id": f"{unique_id}_{entity_id}" if len(entity_ids) > 1 else unique_id} if unique_id else {}
                ),
                **entity_kwargs,
            }
            for entity_id in entity_ids
        },
    )


async def migrate_legacy_entry(
    hass: HomeAssistant,
    entry_data: dict,
    version: int,
    **kwargs: Any,  # noqa: ANN401
) -> MockConfigEntry:
    """Add an entry pinned to a legacy version, run migration, and assert the version was bumped."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data, version=version, **kwargs)
    entry.add_to_hass(hass)
    await async_migrate_entry(hass, entry)
    assert entry.version == PowercalcConfigFlow.VERSION
    return entry


async def create_mocked_virtual_power_sensor_entry(
    hass: HomeAssistant,
    name: str = "Test",
    unique_id: str | None = None,
    extra_config: dict | None = None,
) -> config_entries.ConfigEntry:
    return await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: name,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            **(extra_config or {}),
        },
        unique_id,
        name,
    )


def mock_sensors_in_registry(
    hass: HomeAssistant,
    power_entities: list[str] | None = None,
    energy_entities: list[str] | None = None,
) -> EntityRegistry:
    """Register power and/or energy sensors, named after their entity id."""
    return mock_entities_in_registry(
        hass,
        {
            **{eid: {"name": eid, "device_class": SensorDeviceClass.POWER} for eid in power_entities or []},
            **{eid: {"name": eid, "device_class": SensorDeviceClass.ENERGY} for eid in energy_entities or []},
        },
    )


async def set_states(hass: HomeAssistant, states: list[StateDefinition], block_count: int = 1) -> None:
    for state_definition in states:
        force_update = False
        if len(state_definition) == 2:
            entity_id, value = state_definition
            attributes = None
        elif len(state_definition) == 3:
            entity_id, value, attributes = state_definition
        else:
            entity_id, value, attributes, force_update = state_definition
        hass.states.async_set(entity_id, value, attributes, force_update=force_update)
    for _ in range(block_count):
        await hass.async_block_till_done()


async def async_advance_time(hass: HomeAssistant, delta: timedelta | float, block: bool = True) -> None:
    """Fire a time changed event `delta` into the future, a plain number meaning seconds.

    Pass `block=False` for the rare test that must inspect state before pending jobs are flushed.
    """
    if not isinstance(delta, timedelta):
        delta = timedelta(seconds=delta)
    async_fire_time_changed(hass, dt.utcnow() + delta)
    if block:
        await hass.async_block_till_done()


def assert_entity_state(
    hass: HomeAssistant,
    entity_id: str,
    expected_state: StateType = None,
    attributes: Mapping[str, Any] | None = None,
) -> None:
    """Assert an entity exists and, when given, that its state and attributes match.

    Pass `expected_state=None` to only assert on the attributes.
    """
    state = hass.states.get(entity_id)
    assert state, f"Entity {entity_id} not found"
    if expected_state is not None:
        assert state.state == expected_state
    for attribute, expected in (attributes or {}).items():
        assert state.attributes.get(attribute) == expected, f"Attribute {attribute} of {entity_id} does not match"
