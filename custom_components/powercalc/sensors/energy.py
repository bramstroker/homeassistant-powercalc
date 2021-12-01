from __future__ import annotations
from datetime import timedelta
from decimal import Decimal

import logging
from typing import Any

from homeassistant.components.integration.sensor import (
    TRAPEZOIDAL_METHOD,
    IntegrationSensor,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.const import (
    DEVICE_CLASS_ENERGY,
    ENERGY_KILO_WATT_HOUR
)
from homeassistant.const import CONF_NAME, TIME_HOURS
from homeassistant.core import callback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.event import async_track_time_interval

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_ENERGY_SENSOR_NAMING,
)
from custom_components.powercalc.migrate import async_migrate_entity_id

from .power import VirtualPowerSensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


async def create_energy_sensor(
    hass: HomeAssistantType,
    sensor_config: dict,
    power_sensor: VirtualPowerSensor,
    source_entity: SourceEntity,
) -> VirtualEnergySensor:
    """Create the energy sensor entity"""

    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = sensor_config.get(CONF_NAME) or source_entity.name
    name = name_pattern.format(name)
    object_id = sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        ENTITY_ID_FORMAT, name_pattern.format(object_id), hass=hass
    )
    unique_id = None
    if source_entity.unique_id:
        unique_id = f"{source_entity.unique_id}_energy"
        async_migrate_entity_id(hass, "sensor", unique_id, entity_id)

    _LOGGER.debug("Creating energy sensor: %s", name)
    return VirtualEnergySensor(
        source_entity=power_sensor.entity_id,
        unique_id=unique_id,
        entity_id=entity_id,
        name=name,
        round_digits=4,
        unit_prefix="k",
        unit_of_measurement=None,
        unit_time=TIME_HOURS,
        integration_method=TRAPEZOIDAL_METHOD,
        powercalc_source_entity=source_entity.entity_id,
        powercalc_source_domain=source_entity.domain,
    )


class VirtualEnergySensor(IntegrationSensor):
    """Virtual energy sensor, totalling kWh"""

    def __init__(
        self,
        source_entity,
        unique_id,
        entity_id,
        name,
        round_digits,
        unit_prefix,
        unit_time,
        unit_of_measurement,
        integration_method,
        powercalc_source_entity: str,
        powercalc_source_domain: str,
    ):
        super().__init__(
            source_entity,
            name,
            round_digits,
            unit_prefix,
            unit_time,
            unit_of_measurement,
            integration_method,
        )
        self._powercalc_source_entity = powercalc_source_entity
        self._powercalc_source_domain = powercalc_source_domain
        self.entity_id = entity_id
        if unique_id:
            self._attr_unique_id = unique_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the acceleration sensor."""
        state_attr = super().extra_state_attributes
        state_attr[ATTR_SOURCE_ENTITY] = self._powercalc_source_entity
        state_attr[ATTR_SOURCE_DOMAIN] = self._powercalc_source_domain
        return state_attr

    @property
    def icon(self):
        return ENERGY_ICON

class DailyEnergySensor(RestoreEntity, SensorEntity):
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(
        self,
        hass: HomeAssistantType,
        name: str,
        value: float,
        unit_of_measurement: str,
        update_frequency: int=10
    ):
        self._hass = hass
        self._attr_name = name
        self._value = value
        self._unit_of_measurement = unit_of_measurement
        self._update_frequency = update_frequency

    async def async_added_to_hass(self):
        """Handle entity which will be added."""

        _LOGGER.info("Added to hass")

        if state := await self.async_get_last_state():
            self._state = Decimal(state.state)
        else:
            self._state = Decimal(0)

        _LOGGER.debug(f"Restoring state: {self._state}")

        @callback
        def refresh(event_time=None):
            self.async_schedule_update_ha_state(True)

        self._timer = async_track_time_interval(
            self.hass, refresh, timedelta(seconds=self._update_frequency)
        )

    def update(self):
        """Update the energy sensor state."""
        _LOGGER.info("Updating energy sensor")
        delta = Decimal(self._value / (86400 * self._update_frequency))
        self._state = self._state + delta
        _LOGGER.debug(f"New state {self._state}")
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        return round(self._state, 4)
