from collections.abc import Mapping
import re
from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import EntitySelector, selector
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.power_profile.power_profile import EntityAutoSelectConfig, PowerProfile


def build_dynamic_field_schema(
    hass: HomeAssistant,
    profile: PowerProfile,
    source_entity: SourceEntity | None,
) -> vol.Schema:
    """Build the profile's custom field schema, restricting entities to the source device when available.

    Prefill entity fields with a unique auto-selection match unless an explicit default is set.
    """
    schema = {}
    for field in profile.custom_fields:
        field_description = field.description or field.label
        field_selector = field.selector
        device_entities: list[er.RegistryEntry] = []
        if "entity" in field.selector and source_entity and source_entity.device_entry:
            entity_reg = er.async_get(hass)
            device_entities = list(entity_reg.entities.get_entries_for_device_id(source_entity.device_entry.id))
            # Build a new selector dict instead of mutating field.selector, which is a reference
            # into the (potentially cached) profile json_data.
            field_selector = {
                **field.selector,
                "entity": {
                    **field.selector["entity"],
                    "include_entities": [
                        entity.entity_id
                        for entity in device_entities
                        if "include_entities" not in field.selector["entity"]
                        or entity.entity_id in field.selector["entity"]["include_entities"]
                    ],
                },
            }

        entity_selector = selector(field_selector)
        default = field.default
        if default is None and field.auto_select and isinstance(entity_selector, EntitySelector):
            default = find_auto_selected_entity(device_entities, entity_selector, field.auto_select)

        key = vol.Required(field.key, description=field_description)
        if default is not None:
            key = vol.Required(field.key, description=field_description, default=default)
        schema[key] = entity_selector
    return vol.Schema(schema)


def find_auto_selected_entity(
    entities: list[er.RegistryEntry],
    entity_selector: EntitySelector,
    auto_select: EntityAutoSelectConfig,
) -> str | None:
    """Return a single enabled match without guessing when the selection is ambiguous."""
    matches = []
    for entity in entities:
        if entity.disabled or not matches_entity_filter(entity, auto_select):
            continue
        if not matches_entity_selector(entity, entity_selector):
            continue
        matches.append(entity.entity_id)

    return matches[0] if len(matches) == 1 else None


def matches_entity_selector(entity: er.RegistryEntry, entity_selector: EntitySelector) -> bool:
    """Check the selector's allowed entities and metadata filters against the registry."""
    config = entity_selector.config
    included = config.get("include_entities")
    if included is not None and entity.entity_id not in included:
        return False
    if entity.entity_id in config.get("exclude_entities", []):
        return False

    top_level_filters = {
        key: value for key, value in config.items() if key in ["domain", "device_class", "integration"]
    }
    if not matches_entity_filter(entity, top_level_filters):
        return False

    # EntitySelector normalizes nested filters to a list of alternatives.
    filters = cast(list[Mapping[str, object]], config.get("filter", [{}]))
    return any(matches_entity_filter(entity, item) for item in filters)


def matches_entity_filter(entity: er.RegistryEntry, filters: Mapping[str, object]) -> bool:
    """Match registry metadata; leave filters requiring other data for manual selection."""
    values = {
        "domain": entity.domain,
        "integration": entity.platform,
        "device_class": entity.device_class or entity.original_device_class,
        "translation_key": entity.translation_key,
    }
    for key, expected in filters.items():
        if key == "unique_id_pattern":
            if not re.search(cast(str, expected), entity.unique_id):
                return False
        elif key not in values or values[key] not in (expected if isinstance(expected, list) else [expected]):
            return False
    return True
