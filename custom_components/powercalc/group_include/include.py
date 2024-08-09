import logging

from homeassistant.components import sensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import Entity

from custom_components.powercalc import DiscoveryManager
from custom_components.powercalc.const import (
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    DATA_CONFIGURED_ENTITIES,
    DATA_DISCOVERY_MANAGER,
    DOMAIN,
)
from custom_components.powercalc.sensors.energy import RealEnergySensor
from custom_components.powercalc.sensors.power import RealPowerSensor

from .filter import (
    FilterOperator,
    create_composite_filter,
)

_LOGGER = logging.getLogger(__name__)


async def resolve_include_entities(
    hass: HomeAssistant,
    include_config: dict,
) -> tuple[list[Entity], list[str]]:
    """ "
    For a given include configuration fetch all power and energy sensors from the HA instance
    """
    discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]

    include_non_powercalc: bool = include_config.get(CONF_INCLUDE_NON_POWERCALC_SENSORS, True)
    resolved_entities: list[Entity] = []
    discoverable_entities: list[str] = []
    source_entities = resolve_include_source_entities(hass, include_config)
    if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
        _LOGGER.debug(
            "Found possible include entities: %s",
            list(source_entities.keys()),
        )
    for source_entity in source_entities.values():
        resolved_entities.extend(
            hass.data[DOMAIN][DATA_CONFIGURED_ENTITIES].get(source_entity.entity_id, []),
        )

        # When we are dealing with a non powercalc sensor, and it's a power or energy sensor,
        # we can include that in the group
        if include_non_powercalc and source_entity and source_entity.domain == sensor.DOMAIN:
            device_class = source_entity.device_class or source_entity.original_device_class
            if device_class == SensorDeviceClass.POWER:
                resolved_entities.append(RealPowerSensor(source_entity.entity_id, source_entity.unit_of_measurement))
            elif device_class == SensorDeviceClass.ENERGY:
                resolved_entities.append(RealEnergySensor(source_entity.entity_id))

        if not resolved_entities and source_entity and await discovery_manager.is_entity_supported(source_entity):
            discoverable_entities.append(source_entity.entity_id)

    return resolved_entities, discoverable_entities


@callback
def resolve_include_source_entities(
    hass: HomeAssistant,
    include_config: dict,
) -> dict[str, entity_registry.RegistryEntry | None]:
    entity_filter = create_composite_filter(include_config, hass, FilterOperator.AND)

    entity_reg = entity_registry.async_get(hass)
    return {entry.entity_id: entry for entry in entity_reg.entities.values() if entity_filter.is_valid(entry)}
