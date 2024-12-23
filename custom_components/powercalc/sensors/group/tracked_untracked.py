from __future__ import annotations

import logging
from enum import StrEnum

from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR
from custom_components.powercalc.const import (
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_GROUP_TRACKED_AUTO,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_MAIN_POWER_SENSOR,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    GroupType,
    UnitPrefix,
)
from custom_components.powercalc.group_include.include import resolve_include_entities
from custom_components.powercalc.sensors.abstract import (
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
    generate_power_sensor_entity_id,
    generate_power_sensor_name,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor
from custom_components.powercalc.sensors.group.subtract import SubtractGroupSensor
from custom_components.powercalc.sensors.power import PowerSensor
from custom_components.powercalc.sensors.utility_meter import create_utility_meters

_LOGGER = logging.getLogger(__name__)


class SensorType(StrEnum):
    TRACKED = "tracked"
    UNTRACKED = "untracked"


async def create_tracked_untracked_group_sensors(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    """Create tracked/untracked group sensors."""

    unique_id = str(config.get(CONF_UNIQUE_ID))
    main_power_sensor = str(config.get(CONF_MAIN_POWER_SENSOR)) if config.get(CONF_MAIN_POWER_SENSOR) else None
    auto_mode = bool(config.get(CONF_GROUP_TRACKED_AUTO))
    config[CONF_DISABLE_EXTENDED_ATTRIBUTES] = True  # prevent adding all entities in the state attributes

    if auto_mode:
        entities, _ = await resolve_include_entities(hass)
        tracked_entities = {entity.entity_id for entity in entities if isinstance(entity, PowerSensor)}
    else:
        tracked_entities = set(config.get(CONF_GROUP_TRACKED_POWER_ENTITIES))  # type: ignore

    if main_power_sensor and main_power_sensor in tracked_entities:
        tracked_entities.remove(main_power_sensor)

    should_create_energy_sensor = bool(config.get(CONF_CREATE_ENERGY_SENSOR, False))

    entities = []
    tracked_sensor = await create_tracked_power_sensor(hass, SensorType.TRACKED, unique_id, config, tracked_entities)
    entities.append(tracked_sensor)
    if should_create_energy_sensor:
        energy_sensor = await create_energy_sensor(hass, SensorType.TRACKED, config, tracked_sensor)
        entities.append(energy_sensor)
        entities.extend(
            await create_utility_meters(
                hass,
                energy_sensor,
                {CONF_UTILITY_METER_NET_CONSUMPTION: True, **config},
            ),
        )

    if main_power_sensor:
        untracked_sensor = await create_untracked_power_sensor(
            hass,
            SensorType.UNTRACKED,
            unique_id,
            config,
            main_power_sensor,
            tracked_sensor.entity_id,
        )
        entities.append(untracked_sensor)
        if should_create_energy_sensor:
            energy_sensor = await create_energy_sensor(hass, SensorType.UNTRACKED, config, untracked_sensor)
            entities.append(energy_sensor)
            entities.extend(
                await create_utility_meters(
                    hass,
                    energy_sensor,
                    {CONF_UTILITY_METER_NET_CONSUMPTION: True, **config},
                ),
            )

    return entities


async def create_tracked_power_sensor(
    hass: HomeAssistant,
    sensor_type: SensorType,
    unique_id: str,
    config: ConfigType,
    tracked_entities: set[str],
) -> GroupedPowerSensor:
    _LOGGER.debug("Creating tracked grouped power sensor, entities: %s", tracked_entities)
    unique_id = f"{unique_id}_{sensor_type}_power"
    entity_id = generate_power_sensor_entity_id(hass, config, name=sensor_type, unique_id=unique_id)
    name = generate_power_sensor_name(config, name=sensor_type)
    return GroupedPowerSensor(
        hass,
        sensor_config=config,
        group_type=GroupType.TRACKED_UNTRACKED,
        entities=tracked_entities,
        entity_id=entity_id,
        name=name,
        unique_id=unique_id,
    )


async def create_untracked_power_sensor(
    hass: HomeAssistant,
    sensor_type: SensorType,
    unique_id: str,
    config: ConfigType,
    main_power_entity_id: str,
    tracked_entity_id: str,
) -> GroupedPowerSensor:
    _LOGGER.debug("Creating untracked grouped power sensor")
    unique_id = f"{unique_id}_{sensor_type}_power"
    entity_id = generate_power_sensor_entity_id(hass, config, name=sensor_type, unique_id=unique_id)
    name = generate_power_sensor_name(config, name=sensor_type)
    return SubtractGroupSensor(
        hass,
        entity_id=entity_id,
        name=name,
        sensor_config=config,
        base_entity_id=main_power_entity_id,
        subtract_entities=[tracked_entity_id],
        unique_id=unique_id,
    )


async def create_energy_sensor(
    hass: HomeAssistant,
    sensor_type: SensorType,
    config: ConfigType,
    power_sensor: GroupedPowerSensor,
) -> VirtualEnergySensor:
    """Create an energy sensor for a power sensor."""
    _LOGGER.debug("Creating %s grouped energy sensor", sensor_type)
    unique_id = f"{power_sensor.unique_id}_{sensor_type}_energy"
    name = generate_energy_sensor_name(config, sensor_type)
    entity_id = generate_energy_sensor_entity_id(hass, config, name=sensor_type, unique_id=unique_id)
    return VirtualEnergySensor(
        source_entity=power_sensor.entity_id,
        entity_id=entity_id,
        name=name,
        unique_id=unique_id,
        sensor_config=config,
        unit_prefix=config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX, UnitPrefix.KILO),
    )
