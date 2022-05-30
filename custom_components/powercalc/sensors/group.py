from __future__ import annotations

import logging
from decimal import Decimal, DecimalException
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
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    DOMAIN,
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
    entity_id = await create_entity_id(hass, name, unique_id)
    group_sensors.append(
        GroupedPowerSensor(
            name=name,
            entities=power_sensor_ids,
            unique_id=unique_id,
            rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION),
            entity_id=entity_id,
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
    entity_id = await create_entity_id(hass, name, energy_unique_id)
    group_energy_sensor = GroupedEnergySensor(
        name=name,
        entities=energy_sensor_ids,
        unique_id=energy_unique_id,
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
        entity_id=entity_id,
    )
    group_sensors.append(group_energy_sensor)
    _LOGGER.debug("Creating grouped energy sensor: %s", name)

    group_sensors.extend(
        await create_utility_meters(hass, group_energy_sensor, sensor_config)
    )

    return group_sensors


async def create_entity_id(hass: HomeAssistantType, name: str, unique_id: str | None):
    """
    Check if we already have an entity id based on the unique id of the group sensor
    When this is not the case we generate one using same algorithm as HA add entity routine
    """
    if unique_id is not None:
        ent_reg = entity_registry.async_get(hass)
        if entity_id := ent_reg.async_get_entity_id(
            SENSOR_DOMAIN, SENSOR_DOMAIN, unique_id
        ):
            return entity_id

    return async_generate_entity_id(ENTITY_ID_FORMAT, name, hass=hass)


class GroupedSensor(RestoreEntity, SensorEntity):
    """Base class for grouped sensors"""

    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        entities: list[str],
        entity_id: str,
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
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            self._attr_native_value = state.state

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

        if (
            self._attr_state_class == STATE_CLASS_TOTAL_INCREASING
            and not self.is_state_value_increasing(summed)
        ):
            return

        self._attr_native_value = round(summed, self._rounding_digits)
        self.async_schedule_update_ha_state(True)

    def is_state_value_increasing(self, new_value) -> bool:
        """
        Check to make sure the new state is higer than the previous state
        When this is not the case reject the recording of the state and raise a warning.
        This could happen when an entity of the grouped sensor becomes unavailable for example.
        When we would record this state change it will cause problems down the road with utility meters
        """
        if self._attr_native_value is None or self._attr_native_value in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return True

        try:
            current_value = Decimal(self._attr_native_value)
            if new_value < current_value:
                _LOGGER.warning(
                    "%s: State value of grouped energy sensor may never be lower than last value, skipping. old_value=%s. new_value=%s",
                    self.entity_id,
                    current_value,
                    new_value,
                )
                return False
        except (DecimalException, ValueError) as err:
            _LOGGER.warning(
                "%s: Could not convert to decimal %s: %s",
                self.entity_id,
                current_value,
                err,
            )
            return False

        return True


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
