from __future__ import annotations

import logging
from decimal import Decimal
from typing import cast

from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_GROUP_TRACKED_AUTO, CONF_MAIN_POWER_SENSOR, CONF_POWER_SENSOR_PRECISION,
    CONF_SUBTRACT_ENTITIES,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    DEFAULT_POWER_SENSOR_PRECISION,
    GroupType,
)
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.sensors.abstract import generate_power_sensor_entity_id, generate_power_sensor_name
from custom_components.powercalc.sensors.energy import create_energy_sensor
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor
from custom_components.powercalc.sensors.group.subtract import SubtractGroupSensor
from custom_components.powercalc.sensors.utility_meter import create_utility_meters

_LOGGER = logging.getLogger(__name__)


async def create_tracked_untracked_group_sensors(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    """Create subtract group sensors."""

    #validate_config(config)
    main_power_sensor = str(config.get(CONF_MAIN_POWER_SENSOR))
    auto_mode = bool(config.get(CONF_GROUP_TRACKED_AUTO))
    tracked_entities = set()
    if auto_mode:
        tracked_entities = await resolve_tracked_entities()

    #tracked_name = generate_power_sensor_name(config, "Tracked")
    tracked_unique_id = config.get(CONF_UNIQUE_ID) + "_tracked"
    tracked_entity_id = generate_power_sensor_entity_id(
        hass,
        config,
        name="Tracked",
        unique_id=tracked_unique_id,
    )
    #untracked_name = generate_power_sensor_name(config, "Untracked")
    untracked_unique_id = config.get(CONF_UNIQUE_ID) + "_untracked"
    untracked_entity_id = generate_power_sensor_entity_id(
        hass,
        config,
        name="Untracked",
        unique_id=untracked_unique_id,
    )

    #_LOGGER.debug("Creating grouped power sensor: %s (entity_id=%s)", name, entity_id)

    sensors: list[Entity] = []
    tracked_sensor = GroupedPowerSensor(
        hass,
        sensor_config=config,
        rounding_digits=2,
        group_type=GroupType.TRACKED_UNTRACKED,
        entities=tracked_entities,
        entity_id=tracked_entity_id,
        name="Tracked",
    )
    sensors.append(tracked_sensor)

    untracked_sensor = SubtractGroupSensor(
        hass,
        entity_id=untracked_entity_id,
        name="Untracked",
        sensor_config=config,
        base_entity_id=main_power_sensor,
        subtract_entities=[tracked_sensor.entity_id],
    )
    sensors.append(untracked_sensor)

    return sensors

async def resolve_tracked_entities() -> set[str]:
    """Resolve tracked entities."""
    return set("sensor.1_power")

def generate_unique_id(sensor_config: ConfigType) -> str:
    """Generate unique_id for subtract group sensor."""
    base_entity_id = str(sensor_config[CONF_ENTITY_ID])
    return f"pc_subtract_{base_entity_id}"


def validate_config(config: ConfigType) -> None:
    """Validate subtract group sensor configuration."""
    if CONF_NAME not in config:
        raise SensorConfigurationError("name is required")

    if CONF_ENTITY_ID not in config:
        raise SensorConfigurationError("entity_id is required")

    if CONF_SUBTRACT_ENTITIES not in config:
        raise SensorConfigurationError("subtract_entities is required")
