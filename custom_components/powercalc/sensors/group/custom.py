from __future__ import annotations

import logging
import time
from abc import abstractmethod
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal, DecimalException
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_DEVICE,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import (
    Event,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import start
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    EnergyConverter,
    PowerConverter,
)

from custom_components.powercalc import CONF_GROUP_UPDATE_INTERVAL
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    CONF_AREA,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_EXCLUDE_ENTITIES,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_ENERGY_START_AT_ZERO,
    CONF_GROUP_MEMBER_DEVICES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_HIDE_MEMBERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    DATA_DOMAIN_ENTITIES,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_POWER_SENSOR_PRECISION,
    DOMAIN,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    SERVICE_RESET_ENERGY,
    GroupType,
    SensorType,
    UnitPrefix,
)
from custom_components.powercalc.device_binding import get_device_info
from custom_components.powercalc.group_include.filter import AreaFilter, CompositeFilter, DeviceFilter, EntityFilter, FilterOperator
from custom_components.powercalc.group_include.include import find_entities
from custom_components.powercalc.sensors.abstract import (
    BaseEntity,
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
    generate_power_sensor_entity_id,
    generate_power_sensor_name,
)
from custom_components.powercalc.sensors.energy import EnergySensor, VirtualEnergySensor
from custom_components.powercalc.sensors.power import PowerSensor
from custom_components.powercalc.sensors.utility_meter import create_utility_meters

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = "powercalc_group"
STORAGE_VERSION = 2
# How long between periodically saving the current states to disk
STATE_DUMP_INTERVAL = timedelta(minutes=10)

ENERGY_UNIT_PREFIX_MAPPING = {
    UnitPrefix.KILO: UnitOfEnergy.KILO_WATT_HOUR,
    UnitPrefix.MEGA: UnitOfEnergy.MEGA_WATT_HOUR,
    UnitPrefix.NONE: UnitOfEnergy.WATT_HOUR,
}

UNIT_CONVERTERS: dict[str | None, type[BaseUnitConverter]] = {
    **dict.fromkeys(EnergyConverter.VALID_UNITS, EnergyConverter),
    **dict.fromkeys(PowerConverter.VALID_UNITS, PowerConverter),
}


async def create_group_sensors_yaml(
    hass: HomeAssistant,
    sensor_config: dict[str, Any],
    entities: list[Entity],
    filters: list[Callable] | None = None,
) -> list[Entity]:
    """Create grouped power and energy sensors."""
    power_sensor_ids = filter_entity_list_by_class(entities, PowerSensor, filters)

    create_energy_sensor: bool = sensor_config.get(CONF_CREATE_ENERGY_SENSOR, True)
    energy_sensor_ids = []
    if create_energy_sensor:
        energy_sensor_ids = filter_entity_list_by_class(
            entities,
            EnergySensor,
            filters,
        )

    group_name = str(sensor_config.get(CONF_CREATE_GROUP))
    return await create_group_sensors_custom(hass, group_name, sensor_config, set(power_sensor_ids), set(energy_sensor_ids))


async def create_group_sensors_gui(
    hass: HomeAssistant,
    entry: ConfigEntry,
    sensor_config: dict,
) -> list[Entity]:
    """Create group sensors based on a config_entry."""
    group_name = str(entry.data.get(CONF_NAME))

    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    if not unique_id:
        sensor_config[CONF_UNIQUE_ID] = entry.entry_id

    power_sensor_ids = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.POWER)

    energy_sensor_ids = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.ENERGY)

    return await create_group_sensors_custom(hass, group_name, sensor_config, power_sensor_ids, energy_sensor_ids)


async def create_group_sensors_custom(
    hass: HomeAssistant,
    group_name: str,
    sensor_config: dict[str, Any],
    power_sensor_ids: set[str],
    energy_sensor_ids: set[str],
    force_create: bool = False,
) -> list[Entity]:
    """Create grouped power and energy sensors."""

    group_sensors: list[Entity] = []
    if CONF_NAME not in sensor_config:
        sensor_config[CONF_NAME] = group_name

    group_type: GroupType = GroupType(sensor_config.get(CONF_GROUP_TYPE, GroupType.CUSTOM))

    power_sensor = None
    if power_sensor_ids or force_create:
        power_sensor = create_grouped_power_sensor(
            hass,
            group_name,
            group_type,
            sensor_config,
            set(power_sensor_ids),
        )
        group_sensors.append(power_sensor)

    create_energy_sensor: bool = sensor_config.get(CONF_CREATE_ENERGY_SENSOR, True)
    if create_energy_sensor:
        energy_sensor = create_grouped_energy_sensor(
            hass,
            group_name,
            group_type,
            sensor_config,
            set(energy_sensor_ids),
            power_sensor,
        )

        group_sensors.append(energy_sensor)

        sensor_config[CONF_UTILITY_METER_NET_CONSUMPTION] = True
        group_sensors.extend(
            await create_utility_meters(
                hass,
                energy_sensor,
                sensor_config,
            ),
        )

    return group_sensors


def filter_entity_list_by_class(
    all_entities: list,
    class_name: type[EnergySensor | PowerSensor],
    default_filters: list[Callable] | None = None,
) -> list[str]:
    filter_list = default_filters.copy() if default_filters else []
    filter_list.append(lambda elm: not isinstance(elm, GroupedSensor))
    filter_list.append(lambda elm: isinstance(elm, class_name))
    return [
        x.entity_id
        for x in filter(
            lambda x: all(f(x) for f in filter_list),
            all_entities,
        )
    ]


async def resolve_entity_ids_recursively(  # noqa: C901
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_class: SensorDeviceClass,
    resolved_ids: set[str] | None = None,
) -> set[str]:
    """Get all the entity IDs for the current group and all the subgroups."""
    if resolved_ids is None:
        resolved_ids = set()

    def add_member_entry_ids() -> None:
        """Add power/energy sensors from the group member entries."""
        member_entry_ids = entry.data.get(CONF_GROUP_MEMBER_SENSORS) or []
        for member_entry_id in member_entry_ids:
            member_entry = hass.config_entries.async_get_entry(member_entry_id)
            if member_entry is None:
                continue

            key = resolve_key_based_on_device_class(member_entry)
            if key and key in member_entry.data:
                resolved_ids.add(str(member_entry.data.get(key)))

    def resolve_key_based_on_device_class(member_entry: ConfigEntry) -> str | None:
        """Resolve the correct key for power/energy sensor based on device class."""
        if member_entry.data.get(CONF_SENSOR_TYPE) == SensorType.REAL_POWER:
            return CONF_ENTITY_ID if device_class == SensorDeviceClass.POWER else ENTRY_DATA_ENERGY_ENTITY
        return ENTRY_DATA_POWER_ENTITY if device_class == SensorDeviceClass.POWER else ENTRY_DATA_ENERGY_ENTITY

    def add_specified_sensors() -> None:
        """Add additional power/energy sensors specified by the user."""
        conf_key = CONF_GROUP_POWER_ENTITIES if device_class == SensorDeviceClass.POWER else CONF_GROUP_ENERGY_ENTITIES
        resolved_ids.update(entry.data.get(conf_key) or [])

    async def add_device_and_area_entities() -> None:
        """Add entities from the defined areas."""
        if CONF_AREA not in entry.data and CONF_GROUP_MEMBER_DEVICES not in entry.data:
            return

        filters: list[EntityFilter] = []
        if CONF_AREA in entry.data:
            filters.append(AreaFilter(hass, entry.data[CONF_AREA]))
        if CONF_GROUP_MEMBER_DEVICES in entry.data:
            filters.append(DeviceFilter(set(entry.data[CONF_GROUP_MEMBER_DEVICES])))
        entity_filter = CompositeFilter(filters, FilterOperator.OR)

        resolved_area_entities, _ = await find_entities(
            hass,
            entity_filter,
            bool(entry.data.get(CONF_INCLUDE_NON_POWERCALC_SENSORS)),
        )
        area_entities = [
            entity.entity_id
            for entity in resolved_area_entities
            if isinstance(entity, PowerSensor if device_class == SensorDeviceClass.POWER else EnergySensor)
        ]
        resolved_ids.update(area_entities)

    async def add_subgroup_entities() -> None:
        """Recursively add entities from subgroups."""
        subgroups = entry.data.get(CONF_SUB_GROUPS)
        if not subgroups:
            return

        for subgroup_entry_id in subgroups:
            subgroup_entry = hass.config_entries.async_get_entry(subgroup_entry_id)
            if subgroup_entry is None:
                _LOGGER.error("Subgroup config entry not found: %s", subgroup_entry_id)
                continue

            await resolve_entity_ids_recursively(hass, subgroup_entry, device_class, resolved_ids)

    # Process the main logic
    add_member_entry_ids()
    add_specified_sensors()
    await add_device_and_area_entities()
    await add_subgroup_entities()

    return resolved_ids


@callback
def create_grouped_power_sensor(
    hass: HomeAssistant,
    group_name: str,
    group_type: GroupType,
    sensor_config: dict,
    power_sensor_ids: set[str],
) -> GroupedPowerSensor:
    name = generate_power_sensor_name(sensor_config, group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    if not unique_id:
        unique_id = generate_unique_id(sensor_config)
    entity_id = generate_power_sensor_entity_id(
        hass,
        sensor_config,
        name=group_name,
        unique_id=unique_id,
    )

    _LOGGER.debug("Creating grouped power sensor: %s (entity_id=%s)", name, entity_id)

    return GroupedPowerSensor(
        hass=hass,
        name=name,
        entities=power_sensor_ids,
        unique_id=unique_id,
        sensor_config=sensor_config,
        group_type=group_type,
        entity_id=entity_id,
        device_id=sensor_config.get(CONF_DEVICE),
    )


@callback
def create_grouped_energy_sensor(
    hass: HomeAssistant,
    group_name: str,
    group_type: GroupType,
    sensor_config: dict,
    energy_sensor_ids: set[str],
    power_sensor: GroupedPowerSensor | None,
) -> EnergySensor:
    name = generate_energy_sensor_name(sensor_config, group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    energy_unique_id = None
    if unique_id:
        energy_unique_id = f"{unique_id}_energy"
    entity_id = generate_energy_sensor_entity_id(
        hass,
        sensor_config,
        name=group_name,
        unique_id=energy_unique_id,
    )

    _LOGGER.debug("Creating grouped energy sensor: %s (entity_id=%s)", name, entity_id)

    should_create_riemann = bool(sensor_config.get(CONF_FORCE_CALCULATE_GROUP_ENERGY, False))
    if not should_create_riemann and not energy_sensor_ids:
        should_create_riemann = True
    if group_type == GroupType.DOMAIN and sensor_config.get(CONF_DOMAIN) == "all":
        should_create_riemann = False
    if power_sensor and should_create_riemann:
        return VirtualEnergySensor(
            hass=hass,
            source_entity=power_sensor.entity_id,
            entity_id=entity_id,
            name=name,
            unique_id=energy_unique_id,
            sensor_config=sensor_config,
            device_info=get_device_info(hass, sensor_config, None),
            unit_prefix=sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX, UnitPrefix.NONE),
        )

    return GroupedEnergySensor(
        hass=hass,
        name=name,
        entities=energy_sensor_ids,
        unique_id=energy_unique_id,
        sensor_config=sensor_config,
        group_type=group_type,
        entity_id=entity_id,
        device_id=sensor_config.get(CONF_DEVICE),
    )


def generate_unique_id(sensor_config: dict[str, Any]) -> str:
    return str(sensor_config[CONF_NAME])


class GroupedSensor(BaseEntity, RestoreSensor, SensorEntity):
    """Base class for grouped sensors."""

    _attr_should_poll = False
    _unrecorded_attributes = frozenset({ATTR_ENTITIES, ATTR_IS_GROUP})
    _is_energy_sensor = False

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entities: set[str],
        entity_id: str,
        sensor_config: dict[str, Any],
        group_type: GroupType,
        unique_id: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self._attr_name = name
        # Remove own entity from entities, when it happens to be there. To prevent recursion
        entities.discard(entity_id)
        self._entities = entities
        if self._is_energy_sensor:
            self._rounding_digits = int(sensor_config.get(CONF_ENERGY_SENSOR_PRECISION, DEFAULT_ENERGY_SENSOR_PRECISION))
        else:
            self._rounding_digits = int(sensor_config.get(CONF_POWER_SENSOR_PRECISION, DEFAULT_POWER_SENSOR_PRECISION))
        self._attr_suggested_display_precision = self._rounding_digits
        self._sensor_config = sensor_config
        if unique_id:
            self._attr_unique_id = unique_id
        self.entity_id = entity_id
        self.source_device_id = device_id
        self._prev_state_store: PreviousStateStore = PreviousStateStore(hass)
        self._native_value_exact = Decimal(0)
        self._states: dict[str, Decimal] = {}
        self._ignore_unavailable_state = bool(self._sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE))
        self._group_type = group_type
        self._start_time: float = time.time()
        self._last_update_time: float = 0
        self._update_interval: int = int(self._sensor_config.get(CONF_GROUP_UPDATE_INTERVAL, 60))

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        await super().async_added_to_hass()

        if isinstance(self, GroupedEnergySensor):
            await self.restore_last_state()

        self._prev_state_store = await PreviousStateStore.async_get_instance(self.hass)

        self.async_on_remove(start.async_at_start(self.hass, self.on_start))

        self._async_hide_members(self._sensor_config.get(CONF_HIDE_MEMBERS) or False)

    async def async_will_remove_from_hass(self) -> None:
        """This will trigger when entity is about to be removed from HA
        Unhide the entities, when they where hidden before.
        """
        if self._sensor_config.get(CONF_HIDE_MEMBERS) is True:
            self._async_hide_members(False)

    @callback
    def _async_hide_members(self, hide: bool) -> None:
        """Hide/unhide group members."""
        registry = er.async_get(self.hass)
        for entity_id in self._entities:
            registry_entry = registry.async_get(entity_id)
            if not registry_entry:
                continue

            # We don't want to touch devices which are forced hidden by the user
            if registry_entry.hidden_by == er.RegistryEntryHider.USER:
                continue

            hidden_by = er.RegistryEntryHider.INTEGRATION if hide else None
            registry.async_update_entity(entity_id, hidden_by=hidden_by)

    @callback
    def on_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Triggered when one of the group entities changes state."""
        new_state = event.data.get("new_state")
        if not new_state:  # pragma: no cover
            return
        _LOGGER.debug("Group sensor %s. State change for %s: %s", self.entity_id, new_state.entity_id, new_state)
        calculated_new_state = self.calculate_new_state(new_state)
        self.set_new_state(calculated_new_state)

    async def init_domain_group(self) -> None:
        if self._group_type != GroupType.DOMAIN:
            return
        domain = self._sensor_config.get(CONF_DOMAIN)
        if domain == "all":
            entity_registry = er.async_get(self.hass)
            entities = [entity.entity_id for entity in entity_registry.entities.values() if entity.device_class == self.device_class]
        else:
            entities = self.hass.data[DOMAIN].get(DATA_DOMAIN_ENTITIES).get(domain, [])
            entities = filter_entity_list_by_class(
                entities,
                EnergySensor if self._is_energy_sensor else PowerSensor,
            )
        excluded_entities = self._sensor_config.get(CONF_EXCLUDE_ENTITIES) or []
        self._entities = set({entity for entity in entities if entity not in excluded_entities})

    async def on_start(self, _: Any) -> None:  # noqa
        """Initialize group sensor when HA is starting."""
        await self.init_domain_group()

        if not self._entities:
            _LOGGER.warning("No entities for group sensor %s, setting to unavailable", self.entity_id)
            self._attr_available = False
            self.async_write_ha_state()
            return

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._entities,
                self.on_state_change,
            ),
        )

        if not self._sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES, False):
            self._attr_extra_state_attributes = {
                ATTR_ENTITIES: self._entities,
                ATTR_IS_GROUP: True,
            }

        await self.initial_update()

    async def initial_update(self) -> None:
        """Initial update for the group sensor state."""
        all_states = [self.hass.states.get(entity_id) for entity_id in self._entities]
        states: list[State] = list(filter(None, all_states))
        available_states = [state for state in states if state and state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]]
        if not available_states and not self._ignore_unavailable_state:
            new_state: Decimal | str = STATE_UNAVAILABLE
        else:
            new_state = self.calculate_initial_state(available_states, states)
        self.set_new_state(new_state)

    @callback
    def set_new_state(self, state: Decimal | str) -> None:
        """Set the new state and update the entity."""
        if state == STATE_UNAVAILABLE or not isinstance(state, Decimal):
            self._attr_available = self._ignore_unavailable_state
            self.async_write_ha_state()
            return

        current_time = time.time()
        should_throttle = self._should_throttle(current_time)

        write_state = True
        if should_throttle and current_time - self._last_update_time < self._update_interval:
            write_state = False
        self._attr_available = True
        self._set_native_value(state, write_state=write_state)
        if should_throttle and write_state:
            self._last_update_time = current_time

    def _should_throttle(self, current_time: float) -> bool:
        if self._update_interval == 0:
            return False

        if not self._is_energy_sensor:
            return False

        return not current_time - self._start_time < 5

    def _get_state_value_in_native_unit(self, state: State) -> Decimal:
        """Convert value of member entity state to match the unit of measurement of the group sensor."""
        value = state.state
        unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit_of_measurement and self._attr_native_unit_of_measurement != unit_of_measurement:
            converter = UNIT_CONVERTERS[unit_of_measurement]
            convert = converter.converter_factory(unit_of_measurement, self._attr_native_unit_of_measurement)
            value = str(convert(float(value)))
        try:
            return Decimal(value)
        except DecimalException as err:
            _LOGGER.warning(
                "Error converting state value %s to Decimal for %s: %s",
                value,
                state.entity_id,
                err,
            )
            return Decimal(0)

    def _set_native_value(self, value: Decimal, write_state: bool = True) -> None:
        self._native_value_exact = value
        self._attr_native_value = round(value, self._rounding_digits)
        if write_state:
            self.async_write_ha_state()

    @property
    def entities(self) -> set[str]:
        return self._entities

    def get_group_entities(self) -> dict[str, set[str]]:
        return {ATTR_ENTITIES: self._entities}

    @abstractmethod
    def calculate_initial_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal | str:
        """Implementation for the initial state calculation"""

    @abstractmethod
    def calculate_new_state(
        self,
        state: State,
    ) -> Decimal | str:
        """Implementation for the state calculation whenever a member entity changes state"""


class GroupedPowerSensor(GroupedSensor, PowerSensor):
    """Grouped power sensor. Sums all values of underlying individual power sensors."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _is_energy_sensor = False

    def calculate_initial_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal | str:
        self._states = {state.entity_id: self._get_state_value_in_native_unit(state) for state in member_available_states}
        return self.get_summed_state()

    def calculate_new_state(self, state: State) -> Decimal | str:
        if state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            if state.entity_id in self._states:
                del self._states[state.entity_id]
        else:
            self._states[state.entity_id] = self._get_state_value_in_native_unit(state)
        return self.get_summed_state()

    def get_summed_state(self) -> Decimal | str:
        if not self._states:
            if self._ignore_unavailable_state:
                return Decimal(0)
            return STATE_UNAVAILABLE

        return Decimal(sum(self._states.values()))


class GroupedEnergySensor(GroupedSensor, EnergySensor):
    """Grouped energy sensor. Sums all values of underlying individual energy sensors."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _is_energy_sensor = True

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entities: set[str],
        entity_id: str,
        sensor_config: dict[str, Any],
        group_type: GroupType,
        unique_id: str | None = None,
        device_id: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            name,
            entities,
            entity_id,
            sensor_config,
            group_type,
            unique_id,
            device_id,
        )

        self._attr_native_unit_of_measurement = ENERGY_UNIT_PREFIX_MAPPING.get(
            sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX, UnitPrefix.NONE),
            UnitOfEnergy.WATT_HOUR,
        )

    async def async_reset(self) -> None:
        """Reset the group sensor and underlying member sensor when supported."""
        _LOGGER.debug("%s: Reset grouped energy sensor", self.entity_id)
        self._set_native_value(Decimal(0))
        self.async_write_ha_state()

        for entity_id in self._entities:
            _LOGGER.debug("Resetting %s", entity_id)
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_RESET_ENERGY,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
            if self._prev_state_store:
                self._prev_state_store.set_entity_state(
                    self.entity_id,
                    entity_id,
                    State(entity_id, "0.00"),
                )

    async def async_calibrate(self, value: str) -> None:
        _LOGGER.debug("%s: Calibrate group energy sensor to: %s", self.entity_id, value)
        self._set_native_value(Decimal(value))
        self.async_write_ha_state()

    def calculate_initial_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal:
        """Calculate the new group energy sensor state
        For each member sensor we calculate the delta by looking at the previous known state and compare it to the current.
        """
        group_sum = Decimal(self._native_value_exact) if self._native_value_exact else Decimal(0)
        _LOGGER.debug("%s: Recalculate, current value: %s", self.entity_id, group_sum)
        for state in member_available_states:
            group_sum += self.calculate_delta(state)

        _LOGGER.debug(
            "%s: New value: %s",
            self.entity_id,
            round(group_sum, self._rounding_digits),
        )
        return group_sum

    def calculate_new_state(self, state: State) -> Decimal | str:
        group_sum = Decimal(self._native_value_exact) if self._native_value_exact else Decimal(0)
        if state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            if group_sum == 0:
                return STATE_UNAVAILABLE
            _LOGGER.debug(
                "skipping state for %s, sensor unavailable or unknown",
                state.entity_id,
            )
            return group_sum

        _LOGGER.debug("%s: Recalculate, current value: %s", self.entity_id, group_sum)

        group_sum += self.calculate_delta(state)
        _LOGGER.debug(
            "%s: New value: %s",
            self.entity_id,
            round(group_sum, self._rounding_digits),
        )
        return group_sum

    def calculate_delta(self, state: State) -> Decimal:
        """Calculate the delta between the current and previous state."""
        prev_state = self._prev_state_store.get_entity_state(
            self.entity_id,
            state.entity_id,
        )
        cur_state_value = self._get_state_value_in_native_unit(state)
        prev_state_value = self._get_state_value_in_native_unit(prev_state) if prev_state else Decimal(0)
        self._prev_state_store.set_entity_state(
            self.entity_id,
            state.entity_id,
            state,
        )

        start_at_zero = bool(self._sensor_config.get(CONF_GROUP_ENERGY_START_AT_ZERO, True))
        delta = Decimal(0) if not prev_state and start_at_zero else cur_state_value - prev_state_value

        if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
            rounded_delta = round(delta, self._rounding_digits)
            rounded_prev = round(prev_state_value, self._rounding_digits)
            rounded_cur = round(cur_state_value, self._rounding_digits)
            _LOGGER.debug(
                "delta for entity %s: %s, prev=%s, cur=%s",
                state.entity_id,
                rounded_delta,
                rounded_prev,
                rounded_cur,
            )

        if delta < 0:
            _LOGGER.warning(
                "skipping state for %s, probably erroneous value or sensor was reset",
                state.entity_id,
            )
            delta = Decimal(0)

        return delta

    async def restore_last_state(self) -> None:
        """Restore the last known state of the group sensor."""
        last_state = await self.async_get_last_state()
        last_sensor_state = await self.async_get_last_sensor_data()
        try:
            if last_sensor_state and last_sensor_state.native_value:
                self._set_native_value(Decimal(last_sensor_state.native_value))  # type: ignore
            elif last_state:
                self._set_native_value(Decimal(last_state.state))
            _LOGGER.debug(
                "%s: Restoring state: %s",
                self.entity_id,
                self._attr_native_value,
            )
        except DecimalException as err:
            _LOGGER.warning(
                "%s: Could not restore last state: %s",
                self.entity_id,
                err,
            )


class PreviousStateStore:
    @staticmethod
    @singleton("powercalc_group_storage")
    async def async_get_instance(hass: HomeAssistant) -> PreviousStateStore:
        """Get the singleton instance of this data helper."""
        instance = PreviousStateStore(hass)
        instance.states = {}

        try:
            _LOGGER.debug("Load previous energy sensor states from store")
            stored_states = await instance.store.async_load() or {}
            for group, entities in stored_states.items():
                instance.states[group] = {entity_id: State.from_dict(json_state) for (entity_id, json_state) in entities.items()}
        except HomeAssistantError as exc:  # pragma: no cover
            _LOGGER.error("Error loading previous energy sensor states", exc_info=exc)

        instance.async_setup_dump()

        return instance

    def __init__(self, hass: HomeAssistant) -> None:
        self.store: Store = PreviousStateStoreStore(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            encoder=JSONEncoder,
        )
        self.states: dict[str, dict[str, State | None]] = {}
        self.hass = hass

    def get_entity_state(self, group: str, entity_id: str) -> State | None:
        """Retrieve the previous state."""
        if group in self.states and entity_id in self.states[group]:
            return self.states[group][entity_id]

        return None

    def set_entity_state(self, group: str, entity_id: str, state: State) -> None:
        """Set the state for an energy sensor."""
        self.states.setdefault(group, {})[entity_id] = state

    async def persist_states(self) -> None:
        """Save the current states to storage."""
        try:
            await self.store.async_save(self.states)
        except HomeAssistantError as exc:  # pragma: no cover
            _LOGGER.error("Error saving current states", exc_info=exc)

    @callback
    def async_setup_dump(self) -> None:
        """Set up the listeners for persistence."""

        async def _async_dump_states(*_: Any) -> None:  # noqa: ANN401
            await self.persist_states()

        # Dump states periodically
        cancel_interval = async_track_time_interval(
            self.hass,
            _async_dump_states,
            STATE_DUMP_INTERVAL,
        )

        async def _async_dump_states_at_stop(*_: Any) -> None:  # noqa: ANN401
            cancel_interval()
            await self.persist_states()

        # Dump states when stopping hass
        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            _async_dump_states_at_stop,
        )


class PreviousStateStoreStore(Store):
    """Store area registry data."""

    async def _async_migrate_func(  # type: ignore
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Migrate to the new version."""
        if old_major_version == 1:
            return {}
        return old_data  # pragma: no cover
