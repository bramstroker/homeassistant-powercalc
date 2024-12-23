from __future__ import annotations

import logging

from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_GROUP_TRACKED_AUTO,
    CONF_MAIN_POWER_SENSOR,
    GroupType,
)
from custom_components.powercalc.group_include.include import resolve_include_entities
from custom_components.powercalc.sensors.abstract import generate_power_sensor_entity_id
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor
from custom_components.powercalc.sensors.group.subtract import SubtractGroupSensor
from custom_components.powercalc.sensors.power import PowerSensor

_LOGGER = logging.getLogger(__name__)


async def create_tracked_untracked_group_sensors(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    """Create tracked/untracked group sensors."""

    unique_id = str(config.get(CONF_UNIQUE_ID))
    main_power_sensor = str(config.get(CONF_MAIN_POWER_SENSOR))
    auto_mode = bool(config.get(CONF_GROUP_TRACKED_AUTO))

    if auto_mode:
        entities, _ = await resolve_include_entities(hass)
        tracked_entities = {entity.entity_id for entity in entities if isinstance(entity, PowerSensor)}
    else:
        tracked_entities = set()

    if main_power_sensor in tracked_entities:
        tracked_entities.remove(main_power_sensor)

    tracked_unique_id = unique_id + "_tracked"
    tracked_entity_id = generate_power_sensor_entity_id(
        hass,
        config,
        name="Tracked",
        unique_id=tracked_unique_id,
    )
    untracked_unique_id = unique_id + "_untracked"
    untracked_entity_id = generate_power_sensor_entity_id(
        hass,
        config,
        name="Untracked",
        unique_id=untracked_unique_id,
    )

    _LOGGER.debug("Creating tracked grouped power sensor, entities: %s", tracked_entities)

    sensors: list[Entity] = []
    tracked_sensor = GroupedPowerSensor(
        hass,
        sensor_config=config,
        group_type=GroupType.TRACKED_UNTRACKED,
        entities=tracked_entities,
        entity_id=tracked_entity_id,
        name="Tracked power",
        unique_id=tracked_unique_id,
    )
    sensors.append(tracked_sensor)

    untracked_sensor = SubtractGroupSensor(
        hass,
        entity_id=untracked_entity_id,
        name="Untracked power",
        sensor_config=config,
        base_entity_id=main_power_sensor,
        subtract_entities=[tracked_sensor.entity_id],
        unique_id=untracked_unique_id,
    )
    sensors.append(untracked_sensor)

    return sensors
