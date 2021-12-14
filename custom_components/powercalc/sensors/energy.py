from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from homeassistant.components.integration.sensor import (
    TRAPEZOIDAL_METHOD,
    IntegrationSensor,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import STATE_CLASS_TOTAL_INCREASING, SensorEntity
from homeassistant.const import (
    CONF_NAME,
    DEVICE_CLASS_ENERGY,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    TIME_HOURS,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import HomeAssistantType

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
    _attr_should_poll = False
    _attr_icon = ENERGY_ICON

    def __init__(
        self,
        hass: HomeAssistantType,
        name: str,
        value: float,
        unit_of_measurement: str,
        update_frequency: int,
        on_time: timedelta = timedelta(days=1),
    ):
        self._hass = hass
        self._attr_name = name
        self._value = value
        self._unit_of_measurement = unit_of_measurement
        self._update_frequency = update_frequency
        self._on_time = on_time
        self.entity_id = async_generate_entity_id(ENTITY_ID_FORMAT, name, hass=hass)

    async def async_added_to_hass(self):
        """Handle entity which will be added."""

        if state := await self.async_get_last_state():
            self._state = Decimal(state.state)
            delta = self.calculate_delta(
                round(datetime.now().timestamp() - state.last_changed.timestamp())
            )
            self._state = self._state + delta
            self.async_schedule_update_ha_state()
        else:
            self._state = Decimal(0)

        _LOGGER.debug(f"{self.entity_id}: Restoring state: {self._state}")

        @callback
        def refresh(event_time=None):
            """Update the energy sensor state."""
            self._state = self._state + self.calculate_delta(self._update_frequency)
            _LOGGER.debug(
                f"{self.entity_id}: Updating daily_fixed_energy sensor: {self._state}"
            )
            self.async_schedule_update_ha_state()

        self._timer = async_track_time_interval(
            self.hass, refresh, timedelta(seconds=self._update_frequency)
        )

    def calculate_delta(self, elapsedSeconds: int) -> Decimal:
        value = self._value
        if isinstance(value, Template):
            value = value.render()

        if self._unit_of_measurement == ENERGY_KILO_WATT_HOUR:
            kwhPerDay = value
        elif self._unit_of_measurement == POWER_WATT:
            kwhPerDay = (value * (self._on_time.total_seconds() / 3600)) / 1000

        return Decimal((kwhPerDay / 86400) * elapsedSeconds)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return round(self._state, 4)
