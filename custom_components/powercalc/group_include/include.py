import logging
from typing import cast

from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import split_entity_id
from homeassistant.helpers.template import Template

from ..const import CONF_AREA, CONF_FILTER, CONF_GROUP, CONF_TEMPLATE
from ..errors import SensorConfigurationError
from .filter import create_filter

_LOGGER = logging.getLogger(__name__)


@callback
def resolve_include_entities(
    hass: HomeAssistant, include_config: dict
) -> list[entity_registry.RegistryEntry]:
    entities = {}
    entity_reg = entity_registry.async_get(hass)

    # Include entities from a certain area
    if CONF_AREA in include_config:
        area_id = include_config.get(CONF_AREA)
        _LOGGER.debug("Including entities from area: %s", area_id)
        entities = entities | resolve_area_entities(hass, area_id)

    # Include entities from a certain domain
    if CONF_DOMAIN in include_config:
        domain = include_config.get(CONF_DOMAIN)
        _LOGGER.debug("Including entities from domain: %s", domain)
        entities = entities | {
            entity.entity_id: entity
            for entity in entity_reg.entities.values()
            if entity.domain == domain
        }

    # Include entities from a certain group
    if CONF_GROUP in include_config:
        group_id = include_config.get(CONF_GROUP)
        _LOGGER.debug("Including entities from group: %s", group_id)
        entities = entities | resolve_include_groups(hass, group_id)

    # Include entities by evaluating a template
    if CONF_TEMPLATE in include_config:
        template = include_config.get(CONF_TEMPLATE)
        if not isinstance(template, Template):
            raise SensorConfigurationError(
                "include->template is not a correct Template"
            )
        template.hass = hass

        _LOGGER.debug("Including entities from template")
        entity_ids = template.async_render()
        entities = entities | {
            entity_id: entity_reg.async_get(entity_id) for entity_id in entity_ids
        }

    if CONF_FILTER in include_config:
        entity_filter = create_filter(include_config.get(CONF_FILTER))
        entities = {
            entity_id: entity
            for entity_id, entity in entities.items()
            if entity_filter.is_valid(entity)
        }

    return list(entities.values())


@callback
def resolve_include_groups(
    hass: HomeAssistant, group_id: str
) -> dict[str, entity_registry.RegistryEntry]:
    """Get a listing of al entities in a given group"""
    entity_reg = entity_registry.async_get(hass)

    domain = split_entity_id(group_id)[0]
    if domain == LIGHT_DOMAIN:
        return resolve_light_group_entities(hass, group_id)

    group_state = hass.states.get(group_id)
    if group_state is None:
        raise SensorConfigurationError(f"Group state {group_id} not found")
    entity_ids = group_state.attributes.get(ATTR_ENTITY_ID)
    return {entity_id: entity_reg.async_get(entity_id) for entity_id in entity_ids}


def resolve_light_group_entities(
    hass: HomeAssistant,
    group_id: str,
    resolved_entities: dict[str, entity_registry.RegistryEntry] | None = None,
) -> dict[str, entity_registry.RegistryEntry]:
    """
    Resolve all registry entries for a given light group.
    When the light group has sub light groups, we will recursively walk these as well
    """
    if resolved_entities is None:
        resolved_entities = {}

    entity_reg = entity_registry.async_get(hass)
    light_component = cast(EntityComponent, hass.data.get(LIGHT_DOMAIN))
    light_group = next(
        filter(lambda entity: entity.entity_id == group_id, light_component.entities),
        None,
    )
    if light_group is None or light_group.platform.platform_name != GROUP_DOMAIN:
        raise SensorConfigurationError(f"Light group {group_id} not found")

    entity_ids = light_group.extra_state_attributes.get(ATTR_ENTITY_ID)
    for entity_id in entity_ids:
        registry_entry = entity_reg.async_get(entity_id)
        if registry_entry is None:
            continue

        if registry_entry.platform == GROUP_DOMAIN:
            resolve_light_group_entities(
                hass, registry_entry.entity_id, resolved_entities
            )

        resolved_entities[entity_id] = registry_entry

    return resolved_entities


@callback
def resolve_area_entities(
    hass: HomeAssistant, area_id_or_name: str
) -> dict[str, entity_registry.RegistryEntry]:
    """Get a listing of al entities in a given area"""
    area_reg = area_registry.async_get(hass)
    area = area_reg.async_get_area(area_id_or_name)
    if area is None:
        area = area_reg.async_get_area_by_name(str(area_id_or_name))

    if area is None:
        raise SensorConfigurationError(
            f"No area with id or name '{area_id_or_name}' found in your HA instance"
        )

    area_id = area.id
    entity_reg = entity_registry.async_get(hass)

    entities = entity_registry.async_entries_for_area(entity_reg, area_id)

    device_reg = device_registry.async_get(hass)
    # We also need to add entities tied to a device in the area that don't themselves
    # have an area specified since they inherit the area from the device.
    entities.extend(
        [
            entity
            for device in device_registry.async_entries_for_area(device_reg, area_id)
            for entity in entity_registry.async_entries_for_device(
                entity_reg, device.id
            )
            if entity.area_id is None
        ]
    )
    return {entity.entity_id: entity for entity in entities}
