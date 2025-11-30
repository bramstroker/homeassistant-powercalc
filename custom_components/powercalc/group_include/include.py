from dataclasses import dataclass
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
from custom_components.powercalc.sensors.utility_meter import VirtualUtilityMeter

from .filter import CompositeFilter, DomainFilter, EntityFilter, LambdaFilter, get_filtered_entity_list

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FindEntitiesResult:
    resolved: list[Entity]
    discoverable: list[str]


async def find_entities(
    hass: HomeAssistant,
    entity_filter: EntityFilter | None = None,
    include_non_powercalc: bool = True,
    exclude_utility_meters: bool = True,
) -> FindEntitiesResult:
    """
    Based on the given entity filter, fetch all power and energy sensors from the HA instance.
    """
    domain_data = hass.data.get(DOMAIN, {})

    source_entity_powercalc_entity_map: dict[str, list[tuple[Entity, bool]]] = domain_data.get(
        DATA_CONFIGURED_ENTITIES,
        {},
    )
    powercalc_entities: dict[str, Entity] = domain_data.get(
        DATA_ENTITIES,
        {},
    )

    resolved_entities: list[Entity] = []
    discoverable_entities: list[str] = []

    source_entities = await get_filtered_entity_list(hass, _build_filter(entity_filter))

    if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
        _LOGGER.debug("Source entities: %s", [entity.entity_id for entity in source_entities])

    for source_entity in source_entities:
        entity_id = source_entity.entity_id

        mapped = source_entity_powercalc_entity_map.get(entity_id)
        if mapped:
            resolved_entities.extend(entity for entity, _ in mapped)
            continue

        existing = powercalc_entities.get(entity_id)
        if existing:
            resolved_entities.append(existing)
            continue

        is_real_sensor = False

        if source_entity.domain == sensor.DOMAIN:
            if source_entity.platform != DOMAIN and not include_non_powercalc:
                continue

            device_class = source_entity.device_class or source_entity.original_device_class
            if device_class == SensorDeviceClass.POWER:
                resolved_entities.append(RealPowerSensor(entity_id, source_entity.unit_of_measurement))
                is_real_sensor = True
            elif device_class == SensorDeviceClass.ENERGY:
                resolved_entities.append(RealEnergySensor(entity_id))
                is_real_sensor = True

        # No need to discover a profile for something we already resolved as a real sensor
        if is_real_sensor:
            continue

        power_profile = await get_power_profile_by_source_entity(
            hass,
            await create_source_entity(entity_id, hass),
        )
        if power_profile and not await power_profile.needs_user_configuration and power_profile.is_entity_domain_supported(source_entity):
            discoverable_entities.append(entity_id)

    if exclude_utility_meters:
        resolved_entities = [entity for entity in resolved_entities if not isinstance(entity, VirtualUtilityMeter)]

    if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
        _LOGGER.debug("Resolved entities: %s", [entity.entity_id for entity in resolved_entities])
        _LOGGER.debug("Discoverable entities: %s", discoverable_entities)

    return FindEntitiesResult(resolved_entities, discoverable_entities)


def _build_filter(entity_filter: EntityFilter | None) -> EntityFilter:
    base_filter = CompositeFilter(
        [
            DomainFilter(SUPPORTED_DOMAINS),
            LambdaFilter(lambda entity: entity.platform != "utility_meter"),
            LambdaFilter(lambda entity: not str(entity.unique_id).startswith("powercalc_standby_group")),
            LambdaFilter(lambda entity: "tracked_" not in str(entity.unique_id)),
            LambdaFilter(lambda entity: entity.platform != "tasmota" or not str(entity.entity_id).endswith(("_yesterday", "_today"))),
        ],
    )
    if not entity_filter:
        return base_filter

    return CompositeFilter([base_filter, entity_filter])
