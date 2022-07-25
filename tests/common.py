from homeassistant.components import light, sensor
from homeassistant.const import CONF_PLATFORM, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component
from homeassistant.components import input_boolean
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

import custom_components.test.light as test_light_platform
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    DOMAIN,
    CalculationStrategy,
)


async def create_mock_light_entity(
    hass: HomeAssistant,
    entities: test_light_platform.MockLight | list[test_light_platform.MockLight],
) -> tuple[str, str]:
    """Create a mocked light entity, and bind it to a device having a manufacturer/model"""
    entity_registry = er.async_get(hass)
    device_registry = mock_device_registry(hass)
    platform: test_light_platform = getattr(hass.components, "test.light")
    platform.init(empty=True)

    if not isinstance(entities, list):
        entities = [entities]

    platform.ENTITIES.extend(entities)

    assert await async_setup_component(
        hass, light.DOMAIN, {light.DOMAIN: {CONF_PLATFORM: "test"}}
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
            "light", "test", entity.unique_id, device_id=device_entry.id
        )

    return (entity_entry.entity_id, device_entry.id)


async def run_powercalc_setup_yaml_config(
    hass: HomeAssistant, config: list[ConfigType] | ConfigType
):
    if isinstance(config, list):
        for entry in config:
            if CONF_PLATFORM not in entry:
                entry[CONF_PLATFORM] = DOMAIN
    elif CONF_PLATFORM not in config:
        config[CONF_PLATFORM] = DOMAIN

    await async_setup_component(hass, sensor.DOMAIN, {sensor.DOMAIN: config})
    await hass.async_block_till_done()

async def create_input_boolean(hass: HomeAssistant, name: str = "test"):
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {name: None}}
    )
    await hass.async_block_till_done()

async def create_input_booleans(hass: HomeAssistant, names: list[str]):
    [await create_input_boolean(hass, name) for name in names]

def get_simple_fixed_config(entity_id: str, power: float = 50) -> ConfigType:
    return {
        CONF_ENTITY_ID: entity_id,
        CONF_MODE: CalculationStrategy.FIXED,
        CONF_FIXED: {CONF_POWER: power},
    }