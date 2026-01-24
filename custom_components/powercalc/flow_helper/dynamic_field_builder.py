from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import selector
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.power_profile.power_profile import PowerProfile


def build_dynamic_field_schema(hass: HomeAssistant, profile: PowerProfile, source_entity: SourceEntity | None) -> vol.Schema:
    schema = {}
    for field in profile.custom_fields:
        field_description = field.description
        if not field_description:
            field_description = field.label
        key = vol.Required(field.key, description=field_description)

        if "entity" in field.selector and source_entity and source_entity.device_entry:
            entity_reg = er.async_get(hass)
            field.selector["entity"]["include_entities"] = [
                entity.entity_id for entity in entity_reg.entities.get_entries_for_device_id(source_entity.device_entry.id)
            ]

        schema[key] = selector(field.selector)
    return vol.Schema(schema)
