from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.entity_registry import EntityRegistry

from custom_components.powercalc.const import CONF_AREA
from custom_components.powercalc.device_binding import bind_entity_to_registry_metadata


def test_bind_entity_to_registry_metadata_noop_without_entity_id(hass: HomeAssistant) -> None:
    """Binding is a no-op when no entity_id is provided."""
    # Should simply return without raising, even when an area is configured.
    bind_entity_to_registry_metadata(hass, None, None, {CONF_AREA: "living_room"})


def test_bind_entity_to_area_noop_when_already_in_area(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
    area_registry: AreaRegistry,
) -> None:
    """Re-binding an entity to the area it is already in is a no-op."""
    area = area_registry.async_get_or_create("Living room")
    entry = entity_registry.async_get_or_create("sensor", "powercalc", "abc")
    entity_registry.async_update_entity(entry.entity_id, area_id=area.id)

    bind_entity_to_registry_metadata(hass, entry.entity_id, None, {CONF_AREA: area.id})

    assert entity_registry.async_get(entry.entity_id).area_id == area.id
