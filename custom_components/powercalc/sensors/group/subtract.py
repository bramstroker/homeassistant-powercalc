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
    CONF_POWER_SENSOR_PRECISION,
    CONF_SUBTRACT_ENTITIES,
    GroupType,
)
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.sensors.abstract import generate_power_sensor_entity_id, generate_power_sensor_name
from custom_components.powercalc.sensors.energy import create_energy_sensor
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor

_LOGGER = logging.getLogger(__name__)


async def create_subtract_group_sensors(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    """Create subtract group sensors."""

    validate_config(config)
    group_name = str(config.get(CONF_NAME))
    base_entity_id = str(config.get(CONF_ENTITY_ID))
    subtract_entities = cast(list, config.get(CONF_SUBTRACT_ENTITIES))

    name = generate_power_sensor_name(config, group_name)
    unique_id = config.get(CONF_UNIQUE_ID, generate_unique_id(config))
    entity_id = generate_power_sensor_entity_id(
        hass,
        config,
        name=group_name,
        unique_id=unique_id,
    )

    _LOGGER.debug("Creating grouped power sensor: %s (entity_id=%s)", name, entity_id)

    sensors: list[Entity] = []
    power_sensor = SubtractGroupSensor(
        hass,
        group_name,
        config,
        entity_id,
        base_entity_id,
        subtract_entities,
        unique_id=unique_id,
    )
    sensors.append(power_sensor)
    if config.get(CONF_CREATE_ENERGY_SENSORS):
        sensors.append(
            await create_energy_sensor(
                hass,
                config,
                power_sensor,
            ),
        )
    return sensors


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


class SubtractGroupSensor(GroupedPowerSensor):
    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        sensor_config: ConfigType,
        entity_id: str,
        base_entity_id: str,
        subtract_entities: list[str],
        unique_id: str | None = None,
    ) -> None:
        all_entities = {base_entity_id, *subtract_entities}

        super().__init__(
            hass=hass,
            name=name,
            entities=all_entities,
            entity_id=entity_id,
            sensor_config=sensor_config,
            rounding_digits=int(sensor_config.get(CONF_POWER_SENSOR_PRECISION, 2)),
            group_type=GroupType.SUBTRACT,
            unique_id=unique_id,
            device_id=None,
        )

        self._base_entity_id = base_entity_id
        self._subtract_entities = subtract_entities

    def get_summed_state(self) -> Decimal | str:
        base_value = self._states.get(self._base_entity_id)
        if base_value is None:
            return STATE_UNAVAILABLE
        subtracted_value = base_value
        for entity_id in self._subtract_entities:
            subtracted_value -= self._states.get(entity_id, 0)
        return subtracted_value
