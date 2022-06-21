from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import STATE_CLASS_TOTAL_INCREASING, SensorEntity
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    DEVICE_CLASS_ENERGY,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.const import (
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ON_TIME,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
)
from .energy import EnergySensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


async def create_daily_fixed_energy_sensor(
    hass: HomeAssistantType, sensor_config: dict
) -> DailyEnergySensor:
    mode_config = sensor_config.get(CONF_DAILY_FIXED_ENERGY)

    return DailyEnergySensor(
        hass,
        sensor_config.get(CONF_NAME),
        sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY),
        mode_config.get(CONF_VALUE),
        mode_config.get(CONF_UNIT_OF_MEASUREMENT),
        mode_config.get(CONF_UPDATE_FREQUENCY),
        unique_id=sensor_config.get(CONF_UNIQUE_ID),
        on_time=mode_config.get(CONF_ON_TIME),
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
    )

class DailyEnergySensor(RestoreEntity, SensorEntity, EnergySensor):
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_should_poll = False
    _attr_icon = ENERGY_ICON

    def __init__(
        self,
        hass: HomeAssistantType,
        name: str,
        entity_category: str,
        value: float,
        unit_of_measurement: str,
        update_frequency: int,
        unique_id: str = None,
        on_time: timedelta = None,
        rounding_digits: int = 4,
    ):
        self._hass = hass
        self._attr_name = name
        self._attr_entity_category = entity_category
        self._value = value
        self._unit_of_measurement = unit_of_measurement
        self._update_frequency = update_frequency
        self._on_time = on_time or timedelta(days=1)
        self._rounding_digits = rounding_digits
        self._attr_unique_id = unique_id
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
                f"{self.entity_id}: Updating daily_fixed_energy sensor: {round(self._state, 4)}"
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
        return round(self._state, self._rounding_digits)