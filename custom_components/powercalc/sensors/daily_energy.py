from __future__ import annotations

import decimal
import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
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
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_ON_TIME,
    CONF_POWER,
    CONF_START_TIME,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    UnitPrefix,
)

from .abstract import generate_energy_sensor_entity_id, generate_energy_sensor_name
from .energy import EnergySensor
from .power import VirtualPowerSensor, create_virtual_power_sensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

DEFAULT_DAILY_UPDATE_FREQUENCY = 1800
DAILY_FIXED_ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VALUE): vol.Any(vol.Coerce(float), cv.template),
        vol.Optional(
            CONF_UNIT_OF_MEASUREMENT,
            default=UnitOfEnergy.KILO_WATT_HOUR,
        ): vol.In(
            [UnitOfEnergy.KILO_WATT_HOUR, UnitOfPower.WATT],
        ),
        vol.Optional(CONF_ON_TIME, default=timedelta(days=1)): cv.time_period,
        vol.Optional(CONF_START_TIME): cv.time,
        vol.Optional(
            CONF_UPDATE_FREQUENCY,
            default=DEFAULT_DAILY_UPDATE_FREQUENCY,
        ): vol.Coerce(int),
    },
)

_LOGGER = logging.getLogger(__name__)


async def create_daily_fixed_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity | None = None,
) -> DailyEnergySensor:
    mode_config: ConfigType = sensor_config.get(CONF_DAILY_FIXED_ENERGY)  # type: ignore

    name = generate_energy_sensor_name(
        sensor_config,
        sensor_config.get(CONF_NAME),
        source_entity,
    )
    unique_id = sensor_config.get(CONF_UNIQUE_ID) or None
    entity_id = generate_energy_sensor_entity_id(
        hass,
        sensor_config,
        unique_id=unique_id,
        source_entity=source_entity,
    )

    _LOGGER.debug(
        "Creating daily_fixed_energy energy sensor (name=%s, entity_id=%s, unique_id=%s)",
        name,
        entity_id,
        unique_id,
    )

    if CONF_ON_TIME in mode_config:
        on_time = mode_config.get(CONF_ON_TIME)
        if not isinstance(on_time, timedelta):
            on_time = timedelta(seconds=on_time)  # type: ignore
    else:
        on_time = timedelta(days=1)

    return DailyEnergySensor(
        hass,
        name,
        entity_id,
        mode_config.get(CONF_VALUE),  # type: ignore
        mode_config.get(CONF_UNIT_OF_MEASUREMENT),  # type: ignore
        mode_config.get(CONF_UPDATE_FREQUENCY),  # type: ignore
        sensor_config,
        on_time=on_time,
        start_time=mode_config.get(CONF_START_TIME),
        rounding_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),  # type: ignore
    )


async def create_daily_fixed_energy_power_sensor(
    hass: HomeAssistant,
    sensor_config: dict,
    source_entity: SourceEntity,
) -> VirtualPowerSensor | None:
    mode_config: dict = sensor_config.get(CONF_DAILY_FIXED_ENERGY)  # type: ignore

    if mode_config.get(CONF_ON_TIME) != timedelta(days=1):
        return None

    power_value: float = mode_config.get(CONF_VALUE)  # type: ignore
    if mode_config.get(CONF_UNIT_OF_MEASUREMENT) == UnitOfEnergy.KILO_WATT_HOUR:
        power_value = power_value * 1000 / 24

    power_sensor_config = sensor_config.copy()
    power_sensor_config[CONF_FIXED] = {CONF_POWER: power_value}

    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    if unique_id:
        power_sensor_config[CONF_UNIQUE_ID] = f"{unique_id}_power"

    _LOGGER.debug(
        "Creating daily_fixed_energy power sensor (base_name=%s unique_id=%s)",
        sensor_config.get(CONF_NAME),
        unique_id,
    )

    return await create_virtual_power_sensor(
        hass,
        power_sensor_config,
        source_entity,
        None,
    )


class DailyEnergySensor(RestoreEntity, SensorEntity, EnergySensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_should_poll = False
    _attr_icon = ENERGY_ICON

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entity_id: str,
        value: float | Template,
        user_unit_of_measurement: str,
        update_frequency: int,
        sensor_config: dict[str, Any],
        on_time: timedelta | None = None,
        start_time: time | None = None,
        rounding_digits: int = 4,
    ) -> None:
        self._hass = hass
        self._attr_name = name
        self._state: Decimal = Decimal(0)
        self._attr_entity_category = sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY)
        self._value = value
        self._user_unit_of_measurement = user_unit_of_measurement
        self._update_frequency = update_frequency
        self._sensor_config = sensor_config
        self._on_time = on_time or timedelta(days=1)
        self._start_time = start_time
        self._rounding_digits = rounding_digits
        self._attr_unique_id = sensor_config.get(CONF_UNIQUE_ID)
        self.entity_id = entity_id
        self._last_updated: float = dt_util.utcnow().timestamp()
        self._last_delta_calculate: float | None = None
        self.set_native_unit_of_measurement()
        self._update_timer_removal: Callable[[], None] | None = None

    def set_native_unit_of_measurement(self) -> None:
        """Set the native unit of measurement."""
        unit_prefix = self._sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX) or UnitPrefix.KILO
        if unit_prefix == UnitPrefix.KILO:
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif unit_prefix == UnitPrefix.NONE:
            self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        elif unit_prefix == UnitPrefix.MEGA:
            self._attr_native_unit_of_measurement = UnitOfEnergy.MEGA_WATT_HOUR

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        if state := await self.async_get_last_state():
            try:
                self._state = Decimal(state.state)
            except decimal.DecimalException:
                _LOGGER.warning(
                    "%s: Cannot restore state: %s",
                    self.entity_id,
                    state.state,
                )
                self._state = Decimal(0)
            self._last_updated = state.last_changed.timestamp()
            self._state += self.calculate_delta()
            self.async_schedule_update_ha_state()
        else:
            self._state = Decimal(0)

        _LOGGER.debug("%s: Restoring state: %s", self.entity_id, self._state)

        @callback
        def refresh(__: datetime) -> None:
            """Update the energy sensor state."""
            delta = self.calculate_delta(self._update_frequency)
            if delta > 0:
                self._state = self._state + delta
                _LOGGER.debug(
                    "%s: Updating daily_fixed_energy sensor: %.4f",
                    self.entity_id,
                    self._state,
                )
                self.async_schedule_update_ha_state()
                self._last_updated = dt_util.now().timestamp()

        self._update_timer_removal = async_track_time_interval(
            self.hass,
            refresh,
            timedelta(seconds=self._update_frequency),
        )

    def calculate_delta(self, elapsed_seconds: int = 0) -> Decimal:
        if self._last_delta_calculate is None:
            self._last_delta_calculate = self._last_updated

        elapsed_seconds = (int(self._last_delta_calculate) - int(self._last_updated)) + elapsed_seconds
        self._last_delta_calculate = dt_util.utcnow().timestamp()

        value = self._value
        if isinstance(value, Template):
            value.hass = self.hass
            value = float(value.async_render())

        wh_per_day = value * (self._on_time.total_seconds() / 3600) if self._user_unit_of_measurement == UnitOfPower.WATT else value * 1000

        # Convert Wh to the native measurement unit
        energy_per_day = wh_per_day
        if self._attr_native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR:
            energy_per_day = wh_per_day / 1000
        elif self._attr_native_unit_of_measurement == UnitOfEnergy.MEGA_WATT_HOUR:
            energy_per_day = wh_per_day / 1000000

        return Decimal((energy_per_day / 86400) * elapsed_seconds)

    @property
    def native_value(self) -> Decimal:
        """Return the state of the sensor."""
        return Decimal(round(self._state, self._rounding_digits))

    @callback
    def async_reset(self) -> None:
        _LOGGER.debug("%s: Reset energy sensor", self.entity_id)
        self._state = Decimal(0)
        self._attr_last_reset = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_increase(self, value: str) -> None:
        _LOGGER.debug("%s: Increasing energy sensor with %s", self.entity_id, value)
        self._state += Decimal(value)
        self.async_write_ha_state()

    async def async_calibrate(self, value: str) -> None:
        _LOGGER.debug("%s: Calibrate energy sensor with %s", self.entity_id, value)
        self._state = Decimal(value)
        self.async_write_ha_state()
