import logging

from homeassistant.components import sensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import Entity

from custom_components.powercalc import DiscoveryManager
from custom_components.powercalc.const import (
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERY_MANAGER,
    DOMAIN,
)
from custom_components.powercalc.sensors.energy import RealEnergySensor
from custom_components.powercalc.sensors.power import RealPowerSensor

from .filter import IncludeEntityFilter, NullFilter

_LOGGER = logging.getLogger(__name__)


async def resolve_include_entities(
    hass: HomeAssistant,
    entity_filter: IncludeEntityFilter | None = None,
    include_non_powercalc: bool = True,
) -> tuple[list[Entity], list[str]]:
    """ "
    Based on given entity filter fetch all power and energy sensors from the HA instance
    """
    discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]

    resolved_entities: list[Entity] = []
    discoverable_entities: list[str] = []
    source_entities = resolve_include_source_entities(hass, entity_filter or NullFilter())
    if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
        _LOGGER.debug(
            "Found possible include entities: %s",
            list(source_entities.keys()),
        )

    source_entity_powercalc_entity_map: dict[str, list] = hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES]
    powercalc_entities: dict[str, Entity] = hass.data[DOMAIN]["test_entities"]
    for source_entity in source_entities.values():
        if source_entity.entity_id in source_entity_powercalc_entity_map:
            resolved_entities.extend(source_entity_powercalc_entity_map[source_entity.entity_id])
            continue

        if source_entity.entity_id in powercalc_entities:
            resolved_entities.append(powercalc_entities[source_entity.entity_id])
            continue

        if source_entity.domain == sensor.DOMAIN and source_entity.platform != DOMAIN and include_non_powercalc:
            device_class = source_entity.device_class or source_entity.original_device_class
            if device_class == SensorDeviceClass.POWER:
                resolved_entities.append(RealPowerSensor(source_entity.entity_id, source_entity.unit_of_measurement))
            elif device_class == SensorDeviceClass.ENERGY and source_entity.platform != "utility_meter":
                resolved_entities.append(RealEnergySensor(source_entity.entity_id))

        if source_entity and await discovery_manager.is_entity_supported(source_entity, None, log_profile_loading_errors=False):
            discoverable_entities.append(source_entity.entity_id)

    return resolved_entities, discoverable_entities


@callback
def resolve_include_source_entities(
    hass: HomeAssistant,
    entity_filter: IncludeEntityFilter,
) -> dict[str, entity_registry.RegistryEntry]:
    entity_reg = entity_registry.async_get(hass)
    return {entry.entity_id: entry for entry in entity_reg.entities.values() if entity_filter.is_valid(entry) and not entry.disabled}
