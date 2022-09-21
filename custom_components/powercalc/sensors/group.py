from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import ATTR_STATE_CLASS
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_UNIQUE_ID,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR,
    ENERGY_WATT_HOUR,
    POWER_WATT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    DOMAIN,
    SERVICE_RESET_ENERGY,
    SensorType,
    UnitPrefix,
)
from .abstract import (
    BaseEntity,
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
    generate_power_sensor_entity_id,
    generate_power_sensor_name,
)
from .energy import EnergySensor, RealEnergySensor
from .power import PowerSensor, RealPowerSensor
from .utility_meter import create_utility_meters

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


async def create_group_sensors(
    group_name: str,
    sensor_config: dict[str, Any],
    entities: list[SensorEntity, RealPowerSensor, RealEnergySensor],
    hass: HomeAssistant,
    filters: list[Callable, None] = None,
) -> list[GroupedSensor]:
    """Create grouped power and energy sensors."""

    if filters is None:
        filters = []

    def _get_filtered_entity_ids_by_class(
        all_entities: list, default_filters: list[Callable], class_name
    ) -> list[str]:
        filters = default_filters.copy()
        filters.append(lambda elm: not isinstance(elm, GroupedSensor))
        filters.append(lambda elm: isinstance(elm, class_name))
        return [
            x.entity_id
            for x in filter(
                lambda x: all(f(x) for f in filters),
                all_entities,
            )
        ]

    group_sensors = []

    power_sensor_ids = _get_filtered_entity_ids_by_class(entities, filters, PowerSensor)
    power_sensor = create_grouped_power_sensor(
        hass, group_name, sensor_config, set(power_sensor_ids)
    )
    group_sensors.append(power_sensor)

    energy_sensor_ids = _get_filtered_entity_ids_by_class(
        entities, filters, EnergySensor
    )
    energy_sensor = create_grouped_energy_sensor(
        hass, group_name, sensor_config, set(energy_sensor_ids)
    )
    group_sensors.append(energy_sensor)

    group_sensors.extend(
        await create_utility_meters(
            hass, energy_sensor, sensor_config, net_consumption=True
        )
    )

    return group_sensors


async def create_group_sensors_from_config_entry(
    hass: HomeAssistant, entry: ConfigEntry, sensor_config: dict
) -> list[GroupedSensor]:
    """Create group sensors based on a config_entry"""
    group_sensors = []

    group_name = entry.data.get(CONF_NAME)

    power_sensor_ids: set[str] = set(
        resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.POWER)
    )
    if power_sensor_ids:
        power_sensor = create_grouped_power_sensor(
            hass, group_name, sensor_config, power_sensor_ids
        )
        group_sensors.append(power_sensor)

    energy_sensor_ids: set[str] = set(
        resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.ENERGY)
    )
    if energy_sensor_ids:
        energy_sensor = create_grouped_energy_sensor(
            hass, group_name, sensor_config, energy_sensor_ids
        )
        group_sensors.append(energy_sensor)

        group_sensors.extend(
            await create_utility_meters(
                hass, energy_sensor, sensor_config, net_consumption=True
            )
        )

    return group_sensors


async def update_associated_group_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, remove: bool
) -> ConfigEntry | None:
    """
    Update the group config entry when the virtual power config entry is associated to a group
    Adds the sensor to the group on creation of the config entry
    Removes the sensor from the group on removal of the config entry
    """
    sensor_type = config_entry.data.get(CONF_SENSOR_TYPE)
    if sensor_type != SensorType.VIRTUAL_POWER:
        return None
    if CONF_GROUP not in config_entry.data:
        return None

    group_entry_id = config_entry.data.get(CONF_GROUP)
    group_entry = hass.config_entries.async_get_entry(group_entry_id)
    member_sensors = group_entry.data.get(CONF_GROUP_MEMBER_SENSORS) or []

    if remove and config_entry.entry_id in member_sensors:
        member_sensors.remove(config_entry.entry_id)
    elif config_entry.entry_id not in member_sensors:
        member_sensors.append(config_entry.entry_id)

    hass.config_entries.async_update_entry(
        group_entry,
        data={**group_entry.data, CONF_GROUP_MEMBER_SENSORS: member_sensors},
    )
    return group_entry


@callback
def resolve_entity_ids_recursively(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_class: SensorDeviceClass,
    resolved_ids: list[str] | None = None,
) -> list[str]:
    """
    Get all the entity id's for the current group and all the subgroups
    """

    if resolved_ids is None:
        resolved_ids = []

    # Include the power/energy sensors for an existing Virtual Power config entry
    entity_reg = er.async_get(hass)
    member_entry_ids = entry.data.get(CONF_GROUP_MEMBER_SENSORS) or []
    # Unfortunately device_class is not correctly set at this time in the entity_registry
    # So we need to match on state_class.
    state_class = (
        SensorStateClass.MEASUREMENT
        if device_class == SensorDeviceClass.POWER
        else SensorStateClass.TOTAL
    )
    entities = [
        entity_entry.entity_id
        for entity_entry in entity_reg.entities.values()
        if entity_entry.config_entry_id in member_entry_ids
        and entity_entry.capabilities.get(ATTR_STATE_CLASS) == state_class
    ]
    resolved_ids.extend(entities)

    # Include the additional power/energy sensors the user specified
    conf_key = (
        CONF_GROUP_POWER_ENTITIES
        if device_class == SensorDeviceClass.POWER
        else CONF_GROUP_ENERGY_ENTITIES
    )
    resolved_ids.extend(entry.data.get(conf_key) or [])

    # Include the entities from sub groups
    subgroups = entry.data.get(CONF_SUB_GROUPS)
    if not subgroups:
        return resolved_ids

    for subgroup_entry_id in subgroups:
        subgroup_entry = hass.config_entries.async_get_entry(subgroup_entry_id)
        if subgroup_entry is None:
            _LOGGER.error(f"Subgroup config entry not found: {subgroup_entry_id}")
            continue
        resolve_entity_ids_recursively(hass, subgroup_entry, device_class, resolved_ids)
    return resolved_ids


@callback
def create_grouped_power_sensor(
    hass: HomeAssistant,
    group_name: str,
    sensor_config: dict,
    power_sensor_ids: set[str],
) -> GroupedPowerSensor:
    name = generate_power_sensor_name(sensor_config, group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    entity_id = generate_power_sensor_entity_id(
        hass, sensor_config, name=group_name, unique_id=unique_id
    )

    _LOGGER.debug("Creating grouped power sensor: %s (entity_id=%s)", name, entity_id)

    return GroupedPowerSensor(
        name=name,
        entities=power_sensor_ids,
        unique_id=unique_id,
        sensor_config=sensor_config,
        rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION),
        entity_id=entity_id,
    )


@callback
def create_grouped_energy_sensor(
    hass: HomeAssistant,
    group_name: str,
    sensor_config: dict,
    energy_sensor_ids: set[str],
) -> GroupedEnergySensor:
    name = generate_energy_sensor_name(sensor_config, group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    energy_unique_id = None
    if unique_id:
        energy_unique_id = f"{unique_id}_energy"
    entity_id = generate_energy_sensor_entity_id(
        hass, sensor_config, name=group_name, unique_id=energy_unique_id
    )

    _LOGGER.debug("Creating grouped energy sensor: %s (entity_id=%s)", name, entity_id)

    return GroupedEnergySensor(
        name=name,
        entities=energy_sensor_ids,
        unique_id=energy_unique_id,
        sensor_config=sensor_config,
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
        entity_id=entity_id,
    )


class GroupedSensor(BaseEntity, RestoreEntity, SensorEntity):
    """Base class for grouped sensors"""

    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        entities: set[str],
        entity_id: str,
        sensor_config: dict[str, Any],
        unique_id: str | None = None,
        rounding_digits: int = 2,
    ):
        self._attr_name = name
        self._entities = entities
        self._attr_extra_state_attributes = {
            ATTR_ENTITIES: self._entities,
            ATTR_IS_GROUP: True,
        }
        self._rounding_digits = rounding_digits
        self._sensor_config = sensor_config
        if unique_id:
            self._attr_unique_id = unique_id
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            self._attr_native_value = state.state

        async_track_state_change_event(self.hass, self._entities, self.on_state_change)

        self._async_hide_members(self._sensor_config.get(CONF_HIDE_MEMBERS))

    async def async_will_remove_from_hass(self) -> None:
        """
        This will trigger when entity is about to be removed from HA
        Unhide the entities, when they where hidden before
        """
        if self._sensor_config.get(CONF_HIDE_MEMBERS) is True:
            self._async_hide_members(False)

    @callback
    def _async_hide_members(self, hide: True):
        """Hide/unhide group members"""
        registry = er.async_get(self.hass)
        for entity_id in self._entities:
            registry_entry = registry.async_get(entity_id)
            if not registry_entry:
                continue

            hidden_by = er.RegistryEntryHider.INTEGRATION if hide else None
            registry.async_update_entity(entity_id, hidden_by=hidden_by)

    @callback
    def on_state_change(self, event):
        """Triggered when one of the group entities changes state"""
        if self.hass.state != CoreState.running:
            return

        ignored_states = (STATE_UNAVAILABLE, STATE_UNKNOWN)
        all_states = [self.hass.states.get(entity_id) for entity_id in self._entities]
        states: list[State] = list(filter(None, all_states))
        available_states = [
            state for state in states if state and state.state not in ignored_states
        ]

        # Remove members with an incompatible unit of measurement for now
        # Maybe we will convert these units in the future
        for state in available_states:
            unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if (
                unit_of_measurement is None
            ):  # No unit of measurement, probably sensor has been reset
                continue
            if unit_of_measurement != self._attr_native_unit_of_measurement:
                _LOGGER.error(
                    f"Group member '{state.entity_id}' has another unit of measurement '{unit_of_measurement}' than the group '{self.entity_id}' which has '{self._attr_native_unit_of_measurement}', this is not supported yet. Removing this entity from the total sum."
                )
                available_states.remove(state)
                self._entities.remove(state.entity_id)

        if not available_states:
            self._attr_available = False
            self.async_schedule_update_ha_state(True)
            return

        summed = sum(Decimal(state.state) for state in available_states)

        self._attr_native_value = round(summed, self._rounding_digits)
        self._attr_available = True
        self.async_schedule_update_ha_state(True)


class GroupedPowerSensor(GroupedSensor, PowerSensor):
    """Grouped power sensor. Sums all values of underlying individual power sensors"""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = POWER_WATT


class GroupedEnergySensor(GroupedSensor, EnergySensor):
    """Grouped energy sensor. Sums all values of underlying individual energy sensors"""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        name: str,
        entities: list[str],
        entity_id: str,
        sensor_config: dict[str, Any],
        unique_id: str | None = None,
        rounding_digits: int = 2,
    ):
        super().__init__(
            name, entities, entity_id, sensor_config, unique_id, rounding_digits
        )
        unit_prefix = sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX)
        if unit_prefix == UnitPrefix.KILO:
            self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        elif unit_prefix == UnitPrefix.NONE:
            self._attr_native_unit_of_measurement = ENERGY_WATT_HOUR
        elif unit_prefix == UnitPrefix.MEGA:
            self._attr_native_unit_of_measurement = ENERGY_MEGA_WATT_HOUR

    @callback
    def async_reset_energy(self) -> None:
        _LOGGER.debug(f"{self.entity_id}: Reset grouped energy sensor")
        for entity_id in self._entities:
            _LOGGER.debug(f"Resetting {entity_id}")
            self.hass.async_create_task(
                self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_RESET_ENERGY,
                    {ATTR_ENTITY_ID: entity_id},
                )
            )
        self._attr_last_reset = dt_util.utcnow()
        self.async_write_ha_state()
