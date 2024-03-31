from __future__ import annotations

import logging
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
    CONF_ENTITIES,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import (
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import start
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.unit_conversion import (
    EnergyConverter,
    PowerConverter,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    CONF_AREA,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_POWER_SENSOR_PRECISION,
    DOMAIN,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    SERVICE_RESET_ENERGY,
    SensorType,
    UnitPrefix,
)
from custom_components.powercalc.device_binding import get_device_info
from custom_components.powercalc.group_include.include import resolve_include_entities

from .abstract import (
    BaseEntity,
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
    generate_power_sensor_entity_id,
    generate_power_sensor_name,
)
from .energy import EnergySensor, VirtualEnergySensor
from .power import PowerSensor
from .utility_meter import create_utility_meters

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = "powercalc_group"
STORAGE_VERSION = 2
# How long between periodically saving the current states to disk
STATE_DUMP_INTERVAL = timedelta(minutes=10)


async def create_group_sensors_yaml(
    group_name: str,
    sensor_config: dict[str, Any],
    entities: list[Entity],
    hass: HomeAssistant,
    filters: list[Callable] | None = None,
) -> list[Entity]:
    """Create grouped power and energy sensors."""
    if filters is None:
        filters = []

    def _get_filtered_entity_ids_by_class(
        all_entities: list,
        default_filters: list[Callable],
        class_name: Any,  # noqa: ANN401
    ) -> list[str]:
        filter_list = default_filters.copy()
        filter_list.append(lambda elm: not isinstance(elm, GroupedSensor))
        filter_list.append(lambda elm: isinstance(elm, class_name))
        return [
            x.entity_id
            for x in filter(
                lambda x: all(f(x) for f in filter_list),
                all_entities,
            )
        ]

    power_sensor_ids = _get_filtered_entity_ids_by_class(entities, filters, PowerSensor)

    create_energy_sensor: bool = sensor_config.get(CONF_CREATE_ENERGY_SENSOR, True)
    energy_sensor_ids = []
    if create_energy_sensor:
        energy_sensor_ids = _get_filtered_entity_ids_by_class(
            entities,
            filters,
            EnergySensor,
        )

    return await create_group_sensors(hass, group_name, sensor_config, set(power_sensor_ids), set(energy_sensor_ids))


async def create_group_sensors_gui(
    hass: HomeAssistant,
    entry: ConfigEntry,
    sensor_config: dict,
) -> list[Entity]:
    """Create group sensors based on a config_entry."""

    group_name = str(entry.data.get(CONF_NAME))

    if CONF_UNIQUE_ID not in sensor_config:
        sensor_config[CONF_UNIQUE_ID] = entry.entry_id

    power_sensor_ids = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.POWER)

    energy_sensor_ids = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.ENERGY)

    return await create_group_sensors(hass, group_name, sensor_config, power_sensor_ids, energy_sensor_ids)


async def create_group_sensors(
    hass: HomeAssistant,
    group_name: str,
    sensor_config: dict[str, Any],
    power_sensor_ids: set[str],
    energy_sensor_ids: set[str],
) -> list[Entity]:
    """Create grouped power and energy sensors."""

    group_sensors: list[Entity] = []

    power_sensor = None
    if power_sensor_ids:
        power_sensor = create_grouped_power_sensor(
            hass,
            group_name,
            sensor_config,
            set(power_sensor_ids),
        )
        group_sensors.append(power_sensor)

    create_energy_sensor: bool = sensor_config.get(CONF_CREATE_ENERGY_SENSOR, True)
    if create_energy_sensor:
        energy_sensor = create_grouped_energy_sensor(
            hass,
            group_name,
            sensor_config,
            set(energy_sensor_ids),
            power_sensor,
        )

        group_sensors.append(energy_sensor)

        group_sensors.extend(
            await create_utility_meters(
                hass,
                energy_sensor,
                sensor_config,
                net_consumption=True,
            ),
        )

    return group_sensors


async def create_domain_group_sensor(
    hass: HomeAssistant,
    discovery_info: DiscoveryInfoType,
    config: ConfigType,
) -> list[Entity]:
    domain = discovery_info[CONF_DOMAIN]
    sensor_config = config.copy()
    sensor_config[
        CONF_UNIQUE_ID
    ] = f"powercalc_domaingroup_{discovery_info[CONF_DOMAIN]}"
    return await create_group_sensors_yaml(
        f"All {domain}",
        sensor_config,
        discovery_info[CONF_ENTITIES],
        hass,
    )


async def remove_power_sensor_from_associated_groups(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> list[ConfigEntry]:
    """When the user remove a virtual power config entry we need to update all the groups which this sensor belongs to."""
    group_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP
        and config_entry.entry_id in (entry.data.get(CONF_GROUP_MEMBER_SENSORS) or [])
    ]

    for group_entry in group_entries:
        member_sensors = group_entry.data.get(CONF_GROUP_MEMBER_SENSORS) or []
        member_sensors.remove(config_entry.entry_id)

        hass.config_entries.async_update_entry(
            group_entry,
            data={**group_entry.data, CONF_GROUP_MEMBER_SENSORS: member_sensors},
        )

    return group_entries


async def remove_group_from_power_sensor_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> list[ConfigEntry]:
    """When the user removes a group config entry we need to update all the virtual power sensors which reference this group."""
    entries_to_update = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_SENSOR_TYPE) == SensorType.VIRTUAL_POWER
        and entry.data.get(CONF_GROUP) == config_entry.entry_id
    ]

    for group_entry in entries_to_update:
        hass.config_entries.async_update_entry(
            group_entry,
            data={**group_entry.data, CONF_GROUP: None},
        )

    return entries_to_update


async def add_to_associated_group(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> ConfigEntry | None:
    """When the user has set a group on a virtual power config entry,
    we need to add this config entry to the group members sensors and update the group.
    """
    sensor_type = config_entry.data.get(CONF_SENSOR_TYPE)
    if sensor_type != SensorType.VIRTUAL_POWER:
        return None

    if CONF_GROUP not in config_entry.data:
        return None

    group_entry_id = str(config_entry.data.get(CONF_GROUP))
    group_entry = hass.config_entries.async_get_entry(group_entry_id)

    if not group_entry:
        _LOGGER.warning(
            "ConfigEntry %s: Cannot add/remove to group %s. It does not exist.",
            config_entry.title,
            group_entry_id,
        )
        return None

    member_sensors = set(group_entry.data.get(CONF_GROUP_MEMBER_SENSORS) or [])

    # Config entry has already been added to associated group. just skip adding it again
    if config_entry.entry_id in member_sensors:
        return None

    member_sensors.add(config_entry.entry_id)
    hass.config_entries.async_update_entry(
        group_entry,
        data={**group_entry.data, CONF_GROUP_MEMBER_SENSORS: list(member_sensors)},
    )
    return group_entry


async def resolve_entity_ids_recursively(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_class: SensorDeviceClass,
    resolved_ids: set[str] | None = None,
) -> set[str]:
    """Get all the entity id's for the current group and all the subgroups."""
    if resolved_ids is None:
        resolved_ids = set()

    # Include the power/energy sensors for an existing Virtual Power config entry
    member_entry_ids = entry.data.get(CONF_GROUP_MEMBER_SENSORS) or []
    for member_entry_id in member_entry_ids:
        member_entry = hass.config_entries.async_get_entry(member_entry_id)
        if member_entry is None:
            continue
        key = (
            ENTRY_DATA_POWER_ENTITY
            if device_class == SensorDeviceClass.POWER
            else ENTRY_DATA_ENERGY_ENTITY
        )
        if key not in member_entry.data:  # pragma: no cover
            continue

        resolved_ids.update([str(member_entry.data.get(key))])

    # Include the additional power/energy sensors the user specified
    conf_key = (
        CONF_GROUP_POWER_ENTITIES
        if device_class == SensorDeviceClass.POWER
        else CONF_GROUP_ENERGY_ENTITIES
    )
    resolved_ids.update(entry.data.get(conf_key) or [])

    # Include entities from defined areas
    if CONF_AREA in entry.data:
        resolved_area_entities, _ = await resolve_include_entities(
            hass,
            {
                CONF_AREA: entry.data[CONF_AREA],
                CONF_INCLUDE_NON_POWERCALC_SENSORS: entry.data.get(CONF_INCLUDE_NON_POWERCALC_SENSORS),
            },
        )
        area_entities = [
            entity.entity_id
            for entity in resolved_area_entities
            if isinstance(
                entity,
                PowerSensor
                if device_class == SensorDeviceClass.POWER
                else EnergySensor,
            )
        ]
        resolved_ids.update(area_entities)

    # Include the entities from sub groups
    subgroups = entry.data.get(CONF_SUB_GROUPS)
    if not subgroups:
        return resolved_ids

    for subgroup_entry_id in subgroups:
        subgroup_entry = hass.config_entries.async_get_entry(subgroup_entry_id)
        if subgroup_entry is None:
            _LOGGER.error("Subgroup config entry not found: %s", subgroup_entry_id)
            continue
        await resolve_entity_ids_recursively(
            hass, subgroup_entry, device_class, resolved_ids,
        )

    return resolved_ids


async def get_entries_having_subgroup(hass: HomeAssistant, subgroup_entry: ConfigEntry) -> list[ConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP
           and subgroup_entry.entry_id in (entry.data.get(CONF_SUB_GROUPS) or [])
    ]


@callback
def create_grouped_power_sensor(
    hass: HomeAssistant,
    group_name: str,
    sensor_config: dict,
    power_sensor_ids: set[str],
) -> GroupedPowerSensor:
    name = generate_power_sensor_name(sensor_config, group_name)
    unique_id = sensor_config.get(CONF_UNIQUE_ID) or sensor_config.get(group_name)
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
        rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION)
        or DEFAULT_POWER_SENSOR_PRECISION,
        entity_id=entity_id,
        device_id=sensor_config.get(CONF_DEVICE),
    )


@callback
def create_grouped_energy_sensor(
    hass: HomeAssistant,
    group_name: str,
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

    force_calculate_energy = bool(sensor_config.get(CONF_FORCE_CALCULATE_GROUP_ENERGY, False))
    if power_sensor and (force_calculate_energy or not energy_sensor_ids):
        return VirtualEnergySensor(
            source_entity=power_sensor.entity_id,
            entity_id=entity_id,
            name=name,
            unique_id=energy_unique_id,
            sensor_config=sensor_config,
            device_info=get_device_info(hass, sensor_config, None),
        )

    return GroupedEnergySensor(
        hass=hass,
        name=name,
        entities=energy_sensor_ids,
        unique_id=energy_unique_id,
        sensor_config=sensor_config,
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION)
        or DEFAULT_ENERGY_SENSOR_PRECISION,
        entity_id=entity_id,
        device_id=sensor_config.get(CONF_DEVICE),
    )


class GroupedSensor(BaseEntity, RestoreSensor, SensorEntity):
    """Base class for grouped sensors."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entities: set[str],
        entity_id: str,
        sensor_config: dict[str, Any],
        rounding_digits: int,
        unique_id: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self._attr_name = name
        # Remove own entity from entities, when it happens to be there. To prevent recursion
        entities.discard(entity_id)
        self._entities = entities
        if not sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES):
            self._attr_extra_state_attributes = {
                ATTR_ENTITIES: self._entities,
                ATTR_IS_GROUP: True,
            }
        self._rounding_digits = rounding_digits
        self._sensor_config = sensor_config
        if unique_id:
            self._attr_unique_id = unique_id
        self.entity_id = entity_id
        self.source_device_id = device_id
        self._prev_state_store: PreviousStateStore = PreviousStateStore(hass)

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        await super().async_added_to_hass()

        state_listener = self.on_state_change
        if isinstance(self, GroupedEnergySensor):
            last_state = await self.async_get_last_state()
            last_sensor_state = await self.async_get_last_sensor_data()
            try:
                if last_sensor_state and last_sensor_state.native_value:
                    self._attr_native_value = round(
                        Decimal(last_sensor_state.native_value),  # type: ignore
                        self._rounding_digits,
                    )
                elif last_state:
                    self._attr_native_value = round(
                        Decimal(last_state.state),
                        self._rounding_digits,
                    )
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

        self._prev_state_store = await PreviousStateStore.async_get_instance(self.hass)

        if isinstance(self, GroupedPowerSensor):
            self.async_on_remove(start.async_at_start(self.hass, state_listener))

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._entities,
                state_listener,
            ),
        )

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
    def on_state_change(self, _: Any) -> None:  # noqa
        """Triggered when one of the group entities changes state."""

        all_states = [self.hass.states.get(entity_id) for entity_id in self._entities]
        states: list[State] = list(filter(None, all_states))
        available_states = [
            state
            for state in states
            if state and state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]
        ]
        if not available_states:
            if self._sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE):
                if isinstance(self, GroupedPowerSensor):
                    self._attr_native_value = 0
                self._attr_available = True
            else:
                self._attr_available = False
            self.async_write_ha_state()
            return

        summed = self.calculate_new_state(available_states, states)
        self._attr_native_value = round(summed, self._rounding_digits)
        self._attr_available = True
        self.async_write_ha_state()

    def _get_state_value_in_native_unit(self, state: State) -> Decimal:
        """Convert value of member entity state to match the unit of measurement of the group sensor."""
        value = float(state.state)
        unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if (
            unit_of_measurement
            and self._attr_native_unit_of_measurement != unit_of_measurement
        ):
            unit_converter = (
                EnergyConverter
                if isinstance(self, GroupedEnergySensor)
                else PowerConverter
            )
            value = unit_converter.convert(
                value,
                unit_of_measurement,
                self._attr_native_unit_of_measurement,
            )
        return Decimal(value)

    @abstractmethod
    def calculate_new_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal:
        """Logic for the state calculation"""


class GroupedPowerSensor(GroupedSensor, PowerSensor):
    """Grouped power sensor. Sums all values of underlying individual power sensors."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def calculate_new_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal:
        values = [
            self._get_state_value_in_native_unit(state)
            for state in member_available_states
        ]
        return Decimal(sum([value for value in values if value is not None]))


class GroupedEnergySensor(GroupedSensor, EnergySensor):
    """Grouped energy sensor. Sums all values of underlying individual energy sensors."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entities: set[str],
        entity_id: str,
        sensor_config: dict[str, Any],
        rounding_digits: int,
        unique_id: str | None = None,
        device_id: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            name,
            entities,
            entity_id,
            sensor_config,
            rounding_digits,
            unique_id,
            device_id,
        )
        unit_prefix = sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX)
        if unit_prefix == UnitPrefix.KILO:
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif unit_prefix == UnitPrefix.NONE:
            self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        elif unit_prefix == UnitPrefix.MEGA:
            self._attr_native_unit_of_measurement = UnitOfEnergy.MEGA_WATT_HOUR

    async def async_reset(self) -> None:
        """Reset the group sensor and underlying member sensor when supported."""
        _LOGGER.debug("%s: Reset grouped energy sensor", self.entity_id)
        self._attr_native_value = 0
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
        self._attr_native_value = Decimal(value)
        self.async_write_ha_state()

    def calculate_new_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal:
        """Calculate the new group energy sensor state
        For each member sensor we calculate the delta by looking at the previous known state and compare it to the current.
        """
        group_sum = Decimal(self._attr_native_value) if self._attr_native_value else Decimal(0)  # type: ignore
        _LOGGER.debug("%s: Recalculate, current value: %d", self.entity_id, group_sum)
        for entity_state in member_states:
            if entity_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                _LOGGER.debug(
                    "skipping state for %s, sensor unavailable or unknown",
                    entity_state.entity_id,
                )
                continue
            prev_state = self._prev_state_store.get_entity_state(
                self.entity_id,
                entity_state.entity_id,
            )
            cur_state_value = self._get_state_value_in_native_unit(entity_state)

            if prev_state:
                prev_state_value = self._get_state_value_in_native_unit(prev_state)
            else:
                prev_state_value = (
                    cur_state_value if self._attr_native_value else Decimal(0)
                )
            self._prev_state_store.set_entity_state(
                self.entity_id,
                entity_state.entity_id,
                entity_state,
            )

            delta = cur_state_value - prev_state_value
            if _LOGGER.isEnabledFor(logging.DEBUG):  # pragma: no cover
                rounded_delta = round(delta, self._rounding_digits)
                rounded_prev = round(prev_state_value, self._rounding_digits)
                rounded_cur = round(cur_state_value, self._rounding_digits)
                _LOGGER.debug(
                    "delta for entity %s: %s, prev=%s, cur=%s",
                    entity_state.entity_id,
                    rounded_delta,
                    rounded_prev,
                    rounded_cur,
                )
            if delta < 0:
                _LOGGER.warning(
                    "skipping state for %s, probably erroneous value or sensor was reset",
                    entity_state.entity_id,
                )
                continue

            group_sum += delta

        _LOGGER.debug(
            "%s: New value: %s",
            self.entity_id,
            round(group_sum, self._rounding_digits),
        )
        return group_sum


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
                instance.states[group] = {
                    entity_id: State.from_dict(json_state)
                    for (entity_id, json_state) in entities.items()
                }
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
