import os

from homeassistant import config_entries
from homeassistant.components import input_boolean, input_number, light, sensor
from homeassistant.components.light import ColorMode
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIQUE_ID,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType, StateType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.test.light as test_light_platform
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    DOMAIN,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)


async def create_mock_light_entity(
    hass: HomeAssistant,
    entities: test_light_platform.MockLight | list[test_light_platform.MockLight],
) -> tuple[str, str]:
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

        entity_entry = entity_registry.async_get_or_create(
            "light",
            "test",
            entity.unique_id,
            device_id=device_entry.id,
        )
        await hass.async_block_till_done()

    return (entity_entry.entity_id, device_entry.id)


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
    sensor_config: list[ConfigType] | ConfigType,
    domain_config: ConfigType | None = None,
) -> None:
    config = {DOMAIN: domain_config or {}}
    if sensor_config:
        if isinstance(sensor_config, list):
            for entry in sensor_config:
                if CONF_PLATFORM not in entry:
                    entry[CONF_PLATFORM] = DOMAIN
        elif CONF_PLATFORM not in sensor_config:
            sensor_config[CONF_PLATFORM] = DOMAIN

        config.update({sensor.DOMAIN: sensor_config})
        if "sensor" in hass.config.components:
            hass.config.components.remove("sensor")
        assert await async_setup_component(hass, sensor.DOMAIN, config)
        await hass.async_block_till_done()

    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()


async def create_input_boolean(hass: HomeAssistant, name: str = "test") -> None:
    assert await async_setup_component(
        hass,
        input_boolean.DOMAIN,
        {"input_boolean": {name: None}},
    )
    await hass.async_block_till_done()


async def create_input_booleans(hass: HomeAssistant, names: list[str]) -> None:
    [await create_input_boolean(hass, name) for name in names]


async def create_input_number(
    hass: HomeAssistant, name: str, initial_value: int
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


async def create_mocked_virtual_power_sensor_entry(
    hass: HomeAssistant,
    name: str,
    unique_id: str | None,
) -> config_entries.ConfigEntry:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: name,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
        title=name,
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def assert_entity_state(
    hass: HomeAssistant, entity_id: str, expected_state: StateType
) -> None:
    state = hass.states.get(entity_id)
    assert state
    assert state.state == expected_state
