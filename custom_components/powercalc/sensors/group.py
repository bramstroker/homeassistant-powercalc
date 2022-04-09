from __future__ import annotations

import logging
from decimal import Decimal
from typing import Callable

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.const import (
    CONF_UNIQUE_ID,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import State, callback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
)
from custom_components.powercalc.sensors.energy import EnergySensor, RealEnergySensor
from custom_components.powercalc.sensors.power import PowerSensor, RealPowerSensor
from custom_components.powercalc.sensors.utility_meter import create_utility_meters

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


async def create_group_sensors(
    group_name: str,
    sensor_config: dict,
    entities: list[SensorEntity, RealPowerSensor, RealEnergySensor],
    hass: HomeAssistantType,
    filters: list[Callable, None] = [],
) -> list[GroupedSensor]:
    """Create grouped power and energy sensors."""

    def _get_filtered_entity_ids_by_class(
        all_entities: list, default_filters: list[Callable], className
    ) -> list[str]:
        filters = default_filters.copy()
        filters.append(lambda elm: not isinstance(elm, GroupedSensor))
        filters.append(lambda elm: isinstance(elm, className))
        return list(
            map(
                lambda x: x.entity_id,
                list(
                    filter(
                        lambda x: all(f(x) for f in filters),
                        all_entities,
                    )
                ),
            )
        )

    group_sensors = []

    power_sensor_ids = _get_filtered_entity_ids_by_class(entities, filters, PowerSensor)
    name_pattern = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    group_sensors.append(
        GroupedPowerSensor(
            name,
            power_sensor_ids,
            hass,
            unique_id=unique_id,
            rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION),
        )
    )
    _LOGGER.debug(f"Creating grouped power sensor: %s", name)

    energy_sensor_ids = _get_filtered_entity_ids_by_class(
        entities, filters, EnergySensor
    )
    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    energy_unique_id = None
    if unique_id:
        energy_unique_id = f"{unique_id}_energy"
    group_energy_sensor = GroupedEnergySensor(
        name,
        energy_sensor_ids,
        hass,
        unique_id=energy_unique_id,
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
    )
    group_sensors.append(group_energy_sensor)
    _LOGGER.debug("Creating grouped energy sensor: %s", name)

    group_sensors.extend(
        await create_utility_meters(hass, group_energy_sensor, sensor_config)
    )

    return group_sensors


class GroupedSensor(SensorEntity):
    """Base class for grouped sensors"""

    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        entities: list[str],
        hass: HomeAssistantType,
        unique_id: str = None,
        rounding_digits: int = 2,
    ):
        self._attr_name = name
        self._entities = entities
        self._attr_extra_state_attributes = {
            ATTR_ENTITIES: self._entities,
            ATTR_IS_GROUP: True,
        }
        self._rounding_digits = rounding_digits
        if unique_id:
            self._attr_unique_id = unique_id
        self.entity_id = async_generate_entity_id(ENTITY_ID_FORMAT, name, hass=hass)

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        async_track_state_change_event(self.hass, self._entities, self.on_state_change)

    @callback
    def on_state_change(self, event):
        """Triggered when one of the group entities changes state"""
        all_states = [self.hass.states.get(entity_id) for entity_id in self._entities]
        states: list[State] = list(filter(None, all_states))
        ignored_states = (STATE_UNAVAILABLE, STATE_UNKNOWN)
        summed = sum(
            Decimal(state.state)
            for state in states
            if state.state not in ignored_states
        )
        self._attr_native_value = round(summed, self._rounding_digits)
        self.async_schedule_update_ha_state(True)


class GroupedPowerSensor(GroupedSensor, PowerSensor):
    """Grouped power sensor. Sums all values of underlying individual power sensors"""

    _attr_device_class = DEVICE_CLASS_POWER
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_native_unit_of_measurement = POWER_WATT


class GroupedEnergySensor(GroupedSensor, EnergySensor):
    """Grouped energy sensor. Sums all values of underlying individual energy sensors"""

    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
