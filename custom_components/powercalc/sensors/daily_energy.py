from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util.dt import now, get_time_zone

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_FIXED,
    CONF_ON_TIME,
    CONF_POWER,
    CONF_START_TIME,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
)
from custom_components.powercalc.sensors.power import create_virtual_power_sensor

from .energy import EnergySensor
from .power import VirtualPowerSensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

DEFAULT_DAILY_UPDATE_FREQUENCY = 1800
DAILY_FIXED_ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VALUE): vol.Any(vol.Coerce(float), cv.template),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=ENERGY_KILO_WATT_HOUR): vol.In(
            [ENERGY_KILO_WATT_HOUR, POWER_WATT]
        ),
        vol.Optional(CONF_ON_TIME, default=timedelta(days=1)): cv.time_period,
        vol.Optional(CONF_START_TIME): cv.time,
        vol.Optional(
            CONF_UPDATE_FREQUENCY, default=DEFAULT_DAILY_UPDATE_FREQUENCY
        ): vol.Coerce(int),
    }
)

_LOGGER = logging.getLogger(__name__)


async def create_daily_fixed_energy_sensor(
    hass: HomeAssistantType, sensor_config: dict
) -> DailyEnergySensor:
    mode_config: dict = sensor_config.get(CONF_DAILY_FIXED_ENERGY)

    _LOGGER.debug(
        "Creating daily_fixed_energy energy sensor (name=%s unique_id=%s)",
        sensor_config.get(CONF_NAME),
        sensor_config.get(CONF_UNIQUE_ID),
    )

    return DailyEnergySensor(
        hass,
        sensor_config.get(CONF_NAME),
        sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY),
        mode_config.get(CONF_VALUE),
        mode_config.get(CONF_UNIT_OF_MEASUREMENT),
        mode_config.get(CONF_UPDATE_FREQUENCY),
        unique_id=sensor_config.get(CONF_UNIQUE_ID),
        on_time=mode_config.get(CONF_ON_TIME),
        start_time=mode_config.get(CONF_START_TIME),
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
    )


async def create_daily_fixed_energy_power_sensor(
    hass: HomeAssistantType, sensor_config: dict, source_entity: SourceEntity
) -> VirtualPowerSensor | None:
    mode_config: dict = sensor_config.get(CONF_DAILY_FIXED_ENERGY)
    if mode_config.get(CONF_UNIT_OF_MEASUREMENT) != POWER_WATT:
        return None

    if mode_config.get(CONF_ON_TIME) != timedelta(days=1):
        return None

    power_sensor_config = sensor_config.copy()
    power_sensor_config[CONF_FIXED] = {CONF_POWER: mode_config.get(CONF_VALUE)}

    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    if unique_id:
        power_sensor_config[CONF_UNIQUE_ID] = f"{unique_id}_power"

    _LOGGER.debug(
        "Creating daily_fixed_energy power sensor (name=%s unique_id=%s)",
        sensor_config.get(CONF_NAME),
        unique_id,
    )

    return await create_virtual_power_sensor(hass, power_sensor_config, source_entity)


class DailyEnergySensor(RestoreEntity, SensorEntity, EnergySensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
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
        start_time: time = None,
        rounding_digits: int = 4,
    ):
        self._hass = hass
        self._attr_name = name
        self._attr_entity_category = entity_category
        self._value = value
        self._unit_of_measurement = unit_of_measurement
        self._update_frequency = update_frequency
        self._on_time = on_time or timedelta(days=1)
        self._start_time = start_time
        
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
            if delta:
                self._state = self._state + delta
            self.async_schedule_update_ha_state()
        else:
            self._state = Decimal(0)

        _LOGGER.debug(f"{self.entity_id}: Restoring state: {self._state}")

        @callback
        def refresh(event_time=None):
            """Update the energy sensor state."""
            delta = self.calculate_delta(self._update_frequency)
            if delta is None:
                return
            self._state = self._state + delta
            _LOGGER.debug(
                f"{self.entity_id}: Updating daily_fixed_energy sensor: {round(self._state, 4)}"
            )
            self.async_schedule_update_ha_state()

        self._timer = async_track_time_interval(
            self.hass, refresh, timedelta(seconds=self._update_frequency)
        )

    def calculate_delta(self, elapsedSeconds: int) -> Decimal | None:
        value = self._value
        if isinstance(value, Template):
            value = value.render()

        if self._unit_of_measurement == ENERGY_KILO_WATT_HOUR:
            kwhPerDay = value
        elif self._unit_of_measurement == POWER_WATT:
            kwhPerDay = (value * (self._on_time.total_seconds() / 3600)) / 1000

        #start_time = 11:00
        #value = 2000
        #on_time = 3600
        #kwhPerDay = 2

        kwhPerSecond = kwhPerDay / 86400

        if self._start_time:
            current_datetime = now()
            (start, end) = self.get_on_time_period()
            if current_datetime < start:
                _LOGGER.debug("Period not started yet, don't increase")
                return None
            if current_datetime > end:
                _LOGGER.debug("Period ended, add remainder if any")
                return None
            kwhPerSecond = kwhPerDay / self._on_time.total_seconds()

        return Decimal(kwhPerSecond * elapsedSeconds)
    
    def get_on_time_period(self) -> tuple:
        current_datetime = now()
        start = current_datetime.replace(
            hour=self._start_time.hour, minute=self._start_time.minute, second=0
        )
        time_zone = get_time_zone(self._hass.config.time_zone)
        start.astimezone(time_zone)
        end = start + self._on_time
        return (start, end)


    @property
    def native_value(self):
        """Return the state of the sensor."""
        return round(self._state, self._rounding_digits)

    @callback
    def async_reset_energy(self) -> None:
        _LOGGER.debug(f"{self.entity_id}: Reset energy sensor")
        self._state = 0
        self.async_write_ha_state()
