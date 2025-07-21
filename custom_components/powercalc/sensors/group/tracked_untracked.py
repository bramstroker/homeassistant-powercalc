from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

import homeassistant.helpers.entity_registry as er
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_UNIQUE_ID, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED, EventEntityRegistryUpdatedData
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR
from custom_components.powercalc.const import (
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_EXCLUDE_ENTITIES,
    CONF_GROUP_TRACKED_AUTO,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_MAIN_POWER_SENSOR,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    GroupType,
    UnitPrefix,
)
from custom_components.powercalc.group_include.filter import LambdaFilter
from custom_components.powercalc.group_include.include import find_entities
from custom_components.powercalc.sensors.abstract import (
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
    generate_power_sensor_entity_id,
    generate_power_sensor_name,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor, GroupedSensor
from custom_components.powercalc.sensors.group.subtract import SubtractGroupSensor
from custom_components.powercalc.sensors.power import PowerSensor
from custom_components.powercalc.sensors.utility_meter import create_utility_meters

_LOGGER = logging.getLogger(__name__)


class SensorType(StrEnum):
    TRACKED = "tracked"
    UNTRACKED = "untracked"


async def find_auto_tracked_power_entities(hass: HomeAssistant, exclude_entities: set[str] | None = None) -> set[str]:
    """Find tracked power entities."""
    entity_filter = None
    if exclude_entities:
        entity_filter = LambdaFilter(lambda entity: entity.entity_id not in exclude_entities)
    entities, _ = await find_entities(hass, entity_filter)
    return {entity.entity_id for entity in entities if isinstance(entity, PowerSensor) and not isinstance(entity, GroupedSensor)}


class TrackedPowerSensorFactory:
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, config: ConfigType) -> None:
        self.hass = hass
        self.tracked_entities: set[str] = set()
        self.config_entry = config_entry
        self.config = config

    async def create_tracked_untracked_group_sensors(self) -> list[Entity]:
        """Create tracked/untracked group sensors."""

        unique_id = str(self.config.get(CONF_UNIQUE_ID))
        main_power_sensor = str(self.config.get(CONF_MAIN_POWER_SENSOR)) if self.config.get(CONF_MAIN_POWER_SENSOR) else None
        self.config[CONF_DISABLE_EXTENDED_ATTRIBUTES] = True  # prevent adding all entities in the state attributes

        self.tracked_entities = await self.get_tracked_power_entities()
        if main_power_sensor and main_power_sensor in self.tracked_entities:
            self.tracked_entities.remove(main_power_sensor)

        should_create_energy_sensor = bool(self.config.get(CONF_CREATE_ENERGY_SENSOR, False))

        entities: list[Entity] = []
        tracked_sensor = await self.create_tracked_power_sensor(SensorType.TRACKED, unique_id, self.tracked_entities)
        entities.append(tracked_sensor)
        if should_create_energy_sensor:
            energy_sensor = await self.create_energy_sensor(SensorType.TRACKED, tracked_sensor)
            entities.append(energy_sensor)
            entities.extend(
                await create_utility_meters(
                    self.hass,
                    energy_sensor,
                    {CONF_UTILITY_METER_NET_CONSUMPTION: True, **self.config},
                ),
            )

        if main_power_sensor:
            untracked_sensor = await self.create_untracked_power_sensor(
                SensorType.UNTRACKED,
                unique_id,
                main_power_sensor,
                tracked_sensor.entity_id,
            )
            entities.append(untracked_sensor)
            if should_create_energy_sensor:
                energy_sensor = await self.create_energy_sensor(SensorType.UNTRACKED, untracked_sensor)
                entities.append(energy_sensor)
                entities.extend(
                    await create_utility_meters(
                        self.hass,
                        energy_sensor,
                        {CONF_UTILITY_METER_NET_CONSUMPTION: True, **self.config},
                    ),
                )

        return entities

    async def get_tracked_power_entities(self) -> set[str]:
        """
        Get all power entities which are part of the tracked sensor group
        """
        if not bool(self.config.get(CONF_GROUP_TRACKED_AUTO, False)):
            return set(self.config.get(CONF_GROUP_TRACKED_POWER_ENTITIES))  # type: ignore

        # For auto mode, we also want to listen for any changes in the entity registry
        # Dynamically add/remove power sensors from the tracked group
        @callback
        def _start_entity_registry_listener(_: Any) -> None:  # noqa ANN401
            self.hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, self._handle_entity_registry_updated)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start_entity_registry_listener)

        exclude_entities = self.config.get(CONF_EXCLUDE_ENTITIES)
        return await find_auto_tracked_power_entities(self.hass, set(exclude_entities) if exclude_entities else None)

    async def _handle_entity_registry_updated(
        self,
        event: Event[EventEntityRegistryUpdatedData],
    ) -> None:
        """Listen to all entity registry updates and reload the config entry if a power sensor is added/removed."""
        entity_id = event.data["entity_id"]
        action = event.data["action"]

        if action == "update" and "old_entity_id" in event.data:
            if event.data["old_entity_id"] in self.tracked_entities:  # type: ignore
                return await self.reload()
            return None  # pragma: no cover

        if action == "remove" and entity_id in self.tracked_entities:
            return await self.reload()

        if action == "create":
            registry = er.async_get(self.hass)
            entity_entry = registry.async_get(entity_id)
            if entity_entry and entity_entry.original_device_class == SensorDeviceClass.POWER:
                return await self.reload()
        return None

    async def reload(self) -> None:
        """Reload the config entry."""
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

    async def create_tracked_power_sensor(
        self,
        sensor_type: SensorType,
        unique_id: str,
        tracked_entities: set[str],
    ) -> GroupedPowerSensor:
        _LOGGER.debug("Creating tracked grouped power sensor, entities: %s", tracked_entities)
        unique_id = f"{unique_id}_{sensor_type}_power"
        entity_id = generate_power_sensor_entity_id(self.hass, self.config, name=sensor_type, unique_id=unique_id)
        name = generate_power_sensor_name(self.config, name=sensor_type)
        return GroupedPowerSensor(
            self.hass,
            sensor_config=self.config,
            group_type=GroupType.TRACKED_UNTRACKED,
            entities=tracked_entities,
            entity_id=entity_id,
            name=name,
            unique_id=unique_id,
        )

    async def create_untracked_power_sensor(
        self,
        sensor_type: SensorType,
        unique_id: str,
        main_power_entity_id: str,
        tracked_entity_id: str,
    ) -> GroupedPowerSensor:
        _LOGGER.debug("Creating untracked grouped power sensor")
        unique_id = f"{unique_id}_{sensor_type}_power"
        entity_id = generate_power_sensor_entity_id(self.hass, self.config, name=sensor_type, unique_id=unique_id)
        name = generate_power_sensor_name(self.config, name=sensor_type)
        return SubtractGroupSensor(
            self.hass,
            entity_id=entity_id,
            name=name,
            sensor_config=self.config,
            base_entity_id=main_power_entity_id,
            subtract_entities=[tracked_entity_id],
            unique_id=unique_id,
        )

    async def create_energy_sensor(
        self,
        sensor_type: SensorType,
        power_sensor: GroupedPowerSensor,
    ) -> VirtualEnergySensor:
        """Create an energy sensor for a power sensor."""
        _LOGGER.debug("Creating %s grouped energy sensor", sensor_type)
        unique_id = f"{power_sensor.unique_id}_{sensor_type}_energy"
        name = generate_energy_sensor_name(self.config, sensor_type)
        entity_id = generate_energy_sensor_entity_id(self.hass, self.config, name=sensor_type, unique_id=unique_id)
        return VirtualEnergySensor(
            hass=self.hass,
            source_entity=power_sensor.entity_id,
            entity_id=entity_id,
            name=name,
            unique_id=unique_id,
            sensor_config=self.config,
            unit_prefix=self.config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX, UnitPrefix.KILO),
        )
