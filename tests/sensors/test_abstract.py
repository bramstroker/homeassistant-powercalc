from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_AREA
from custom_components.powercalc.device_binding import bind_entity_to_registry_metadata


def test_bind_entity_to_registry_metadata_noop_without_entity_id(hass: HomeAssistant) -> None:
    """Binding is a no-op when no entity_id is provided."""
    # Should simply return without raising, even when an area is configured.
    bind_entity_to_registry_metadata(hass, None, None, {CONF_AREA: "living_room"})
