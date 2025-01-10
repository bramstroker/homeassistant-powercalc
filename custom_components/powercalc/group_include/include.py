import logging

from homeassistant.components import sensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import (
    DATA_CONFIGURED_ENTITIES,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.powercalc.discovery import get_power_profile_by_source_entity
from custom_components.powercalc.power_profile.power_profile import SUPPORTED_DOMAINS
from custom_components.powercalc.sensors.energy import RealEnergySensor
from custom_components.powercalc.sensors.power import RealPowerSensor

from .filter import CompositeFilter, DomainFilter, EntityFilter, LambdaFilter, get_filtered_entity_list

_LOGGER = logging.getLogger(__name__)


async def find_entities(
    hass: HomeAssistant,
    entity_filter: EntityFilter | None = None,
    include_non_powercalc: bool = True,
) -> tuple[list[Entity], list[str]]:
    """ "
    Based on given entity filter fetch all power and energy sensors from the HA instance
    """
    domain_data = hass.data.get(DOMAIN, {})

    resolved_entities: list[Entity] = []
    discoverable_entities: list[str] = []
    source_entities = await get_filtered_entity_list(hass, _build_filter(entity_filter))
    if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
        _LOGGER.debug("Found possible include entities: %s", [entity.entity_id for entity in source_entities])

    source_entity_powercalc_entity_map: dict[str, list] = domain_data.get(DATA_CONFIGURED_ENTITIES, {})
    powercalc_entities: dict[str, Entity] = domain_data.get(DATA_ENTITIES, {})
    for source_entity in source_entities:
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
            elif device_class == SensorDeviceClass.ENERGY:
                resolved_entities.append(RealEnergySensor(source_entity.entity_id))

        power_profile = await get_power_profile_by_source_entity(
            hass,
            await create_source_entity(source_entity.entity_id, hass),
        )
        if power_profile and not await power_profile.needs_user_configuration and power_profile.is_entity_domain_supported(source_entity):
            discoverable_entities.append(source_entity.entity_id)

    return resolved_entities, discoverable_entities


def _build_filter(entity_filter: EntityFilter | None) -> EntityFilter:
    base_filter = CompositeFilter(
        [
            DomainFilter(SUPPORTED_DOMAINS),
            LambdaFilter(lambda entity: entity.platform != "utility_meter"),
        ],
    )
    if not entity_filter:
        return base_filter

    return CompositeFilter([base_filter, entity_filter])
