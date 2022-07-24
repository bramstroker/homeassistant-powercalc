from homeassistant.components import light
from homeassistant.const import CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

import custom_components.test.light as test_light_platform


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
