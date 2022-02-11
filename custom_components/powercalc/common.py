from __future__ import annotations

import re
from typing import NamedTuple

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.components.light import ATTR_SUPPORTED_COLOR_MODES
from homeassistant.core import split_entity_id
from homeassistant.helpers.typing import HomeAssistantType

from .const import DUMMY_ENTITY_ID


class SourceEntity(NamedTuple):
    object_id: str
    entity_id: str
    domain: str
    unique_id: str | None = None
    name: str | None = None
    supported_color_modes: list | None = None
    entity_entry: er.RegistryEntry | None = None
    device_entry: dr.DeviceEntry | None = None


async def create_source_entity(entity_id: str, hass: HomeAssistantType) -> SourceEntity:
    """Create object containing all information about the source entity"""

    if entity_id == DUMMY_ENTITY_ID:
        return SourceEntity(
            object_id=DUMMY_ENTITY_ID, entity_id=DUMMY_ENTITY_ID, domain=DUMMY_ENTITY_ID
        )

    source_entity_domain, source_object_id = split_entity_id(entity_id)

    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get(entity_id)

    dev = dr.async_get(hass)
    if entity_entry and entity_entry.device_id:
        device_entry = dev.async_get(entity_entry.device_id)
    else:
        device_entry = None

    unique_id = None
    supported_color_modes = []
    if entity_entry:
        source_entity_name = entity_entry.name or entity_entry.original_name
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id
        if entity_entry.capabilities:
            supported_color_modes = entity_entry.capabilities.get(
                ATTR_SUPPORTED_COLOR_MODES
            )
    else:
        source_entity_name = source_object_id.replace("_", " ")

    entity_state = hass.states.get(entity_id)
    if entity_state:
        source_entity_name = entity_state.name
        supported_color_modes = entity_state.attributes.get(ATTR_SUPPORTED_COLOR_MODES)

    return SourceEntity(
        source_object_id,
        entity_id,
        source_entity_domain,
        unique_id,
        source_entity_name,
        supported_color_modes or [],
        entity_entry,
        device_entry,
    )


def validate_name_pattern(value: str) -> str:
    """Validate that the naming pattern contains {}."""
    regex = re.compile(r"\{\}")
    if not regex.search(value):
        raise vol.Invalid("Naming pattern must contain {}")
    return value
