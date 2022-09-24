from __future__ import annotations

import logging

from homeassistant.core import callback
from homeassistant.helpers.entity_registry import async_get

_LOGGER = logging.getLogger(__name__)


@callback
def async_migrate_entity_id(
    hass,
    old_entity_id: str,
    new_entity_id: str,
) -> None:
    """Check if entity with old unique ID exists, and if so migrate it to new ID."""

    entity_registry = async_get(hass)
    entry = entity_registry.async_get(old_entity_id)
    if entry is None:
        return

    if old_entity_id == new_entity_id:
        return

    _LOGGER.debug(
        "Migrating entity from old entity ID '%s' to new entity ID '%s'",
        old_entity_id,
        new_entity_id,
    )
    try:
        entity_registry.async_update_entity(old_entity_id, new_entity_id=new_entity_id)
    except ValueError as e:
        _LOGGER.error(
            "Migrating entity from old entity ID '%s' to new entity ID '%s'",
            old_entity_id,
            new_entity_id,
        )
        _LOGGER.error(e)
        entity_registry.async_remove(new_entity_id)
