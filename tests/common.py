import os

import homeassistant.helpers.area_registry as ar
from homeassistant import config_entries
from homeassistant.components import input_boolean, input_number, light
from homeassistant.components.light import ColorMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.normalized_name_base_registry import NormalizedNameBaseRegistryItems
from homeassistant.helpers.typing import ConfigType, StateType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_registry

import custom_components.test.light as test_light_platform
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


async def create_mock_light_entity(
    hass: HomeAssistant,
    entities: test_light_platform.MockLight | list[test_light_platform.MockLight],
) -> None:
    """Create a mocked light entity, and bind it to a device having a manufacturer/model"""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    platform: test_light_platform = getattr(hass.components, "test.light")
    platform.init(empty=True)

    if not isinstance(entities, list):
        entities = [entities]

    platform.ENTITIES.extend(entities)

    assert await async_setup_component(
        hass,
        light.DOMAIN,
        {light.DOMAIN: {CONF_PLATFORM: "test"}},
    )
    await hass.async_block_till_done()

    # Bind to device
    for entity in entities:
        config_entry = MockConfigEntry(domain="test")
        config_entry.add_to_hass(hass)
        device_entry = device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            connections={("dummy", entity.unique_id)},
            manufacturer=entity.manufacturer,
            model=entity.model,
        )

        entity_registry.async_get_or_create(
            "light",
            "test",
            entity.unique_id,
            device_id=device_entry.id,
        )
        await hass.async_block_till_done()


def create_discoverable_light(
    name: str,
    unique_id: str = "99f899fefes",
) -> test_light_platform.MockLight:
    light = test_light_platform.MockLight(name, STATE_ON, unique_id)
    light.manufacturer = "lidl"
    light.model = "HG06462A"
    light.supported_color_modes = [ColorMode.BRIGHTNESS]
    light.brightness = 125
    return light


async def run_powercalc_setup(
    hass: HomeAssistant,
    sensor_config: list[ConfigType] | ConfigType | None = None,
    domain_config: ConfigType | None = None,
) -> None:
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


async def create_input_boolean(hass: HomeAssistant, name: str = "test") -> None:
    assert await async_setup_component(
        hass,
        input_boolean.DOMAIN,
        {"input_boolean": {name: None}},
    )
    await hass.async_block_till_done()


async def create_input_booleans(hass: HomeAssistant, names: list[str]) -> None:
    config = {"input_boolean": {name: None for name in names}}
    assert await async_setup_component(
        hass,
        input_boolean.DOMAIN,
        config,
    )
    await hass.async_block_till_done()


async def create_input_number(
    hass: HomeAssistant,
    name: str,
    initial_value: int,
) -> None:
    assert await async_setup_component(
        hass,
        input_number.DOMAIN,
        {"input_number": {name: {"min": 0, "max": 99999, "initial": initial_value}}},
    )
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
        "testing_config/powercalc_profiles",
        sub_dir,
    )


def get_test_config_dir(append_path: str = "") -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "testing_config",
        append_path,
    )


async def setup_config_entry(
    hass: HomeAssistant,
    entry_data: dict,
    unique_id: str | None = None,
    title: str = "Mock Title",
) -> MockConfigEntry:
    """Setup and add a Powercalc config entry"""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data,
        unique_id=unique_id,
        title=title,
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def create_mocked_virtual_power_sensor_entry(
    hass: HomeAssistant,
    name: str = "Test",
    unique_id: str | None = None,
    extra_config: dict | None = None,
) -> config_entries.ConfigEntry:
    return await setup_config_entry(
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


def mock_area_registry(
    hass: HomeAssistant,
    mock_entries: dict[str, ar.AreaEntry] | None = None,
) -> ar.AreaRegistry:
    """Mock the Area Registry.

    This should only be used if you need to mock/re-stage a clean mocked
    area registry in your current hass object. It can be useful to,
    for example, pre-load the registry with items.

    This mock will thus replace the existing registry in the running hass.

    If you just need to access the existing registry, use the `area_registry`
    fixture instead.
    """
    registry = ar.AreaRegistry(hass)
    registry.areas = NormalizedNameBaseRegistryItems[ar.AreaEntry]()
    if mock_entries:
        for key, entry in mock_entries.items():
            registry.areas[key] = entry

    registry._area_data = registry.areas.data  # noqa: SLF001

    hass.data[ar.DATA_REGISTRY] = registry
    return registry


def mock_sensors_in_registry(
    hass: HomeAssistant,
    power_entities: list[str] | None = None,
    energy_entities: list[str] | None = None,
) -> None:
    entries = {}
    for entity_id in power_entities or []:
        entries[entity_id] = RegistryEntry(
            entity_id=entity_id,
            name=entity_id,
            unique_id=entity_id,
            platform="sensor",
            device_class=SensorDeviceClass.POWER,
        )
    for entity_id in energy_entities or []:
        entries[entity_id] = RegistryEntry(
            entity_id=entity_id,
            name=entity_id,
            unique_id=entity_id,
            platform="sensor",
            device_class=SensorDeviceClass.ENERGY,
        )
    mock_registry(hass, entries)


def assert_entity_state(
    hass: HomeAssistant,
    entity_id: str,
    expected_state: StateType,
) -> None:
    state = hass.states.get(entity_id)
    assert state
    assert state.state == expected_state
