"""Platform for sensor integration."""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from custom_components.powercalc import DOMAIN
from custom_components.powercalc.analytics.analytics import collect_analytics
from custom_components.powercalc.const import DATA_ENTITY_TYPES, EntityType

SIGNAL_CREATE_SELECT_ENTITIES = "powercalc_create_select_entities_{}"
DATA_PENDING_SELECT_ENTITIES = "powercalc_pending_select_entities"


def _key(entry: ConfigEntry | None) -> str:
    return entry.entry_id if entry else ""


_LOGGER = logging.getLogger(__name__)


def delayed_add_entities_handler(
    hass: HomeAssistant,
    async_add_entities: AddEntitiesCallback,
    entry: ConfigEntry | None = None,
) -> Callable[[], None]:
    @callback
    def _handle_new_entities(entities: list[SelectEntity]) -> None:
        _LOGGER.debug("Adding TariffSelect entities signal")
        collect_analytics(hass, entry).inc(DATA_ENTITY_TYPES, EntityType.TARIFF_SELECT)
        async_add_entities(entities)

    return async_dispatcher_connect(
        hass,
        SIGNAL_CREATE_SELECT_ENTITIES.format(_key(entry)),
        _handle_new_entities,
    )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Setup sensors from YAML config sensor entries."""
    key = _key(None)
    pending = hass.data[DOMAIN].setdefault(DATA_PENDING_SELECT_ENTITIES, {}).pop(key, [])
    if pending:  # pragma: no cover
        _LOGGER.debug("Adding TariffSelect entities pending")
        collect_analytics(hass, None).inc(DATA_ENTITY_TYPES, EntityType.TARIFF_SELECT)
        async_add_entities(pending)

    delayed_add_entities_handler(hass, async_add_entities)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup sensors from config entry."""
    key = _key(entry)
    pending = hass.data[DOMAIN].setdefault(DATA_PENDING_SELECT_ENTITIES, {}).pop(key, [])
    if pending:
        _LOGGER.debug("Adding TariffSelect entities pending")
        collect_analytics(hass, entry).inc(DATA_ENTITY_TYPES, EntityType.TARIFF_SELECT)
        async_add_entities(pending)

    unsub = delayed_add_entities_handler(hass, async_add_entities, entry)
    entry.async_on_unload(unsub)
