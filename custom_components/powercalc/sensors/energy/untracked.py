from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.integration.sensor import UNIT_PREFIXES, UNIT_TIME, _IntegrationMethod
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    CONF_NAME,
    UnitOfEnergy,
    UnitOfTime,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import start
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_MIN_TIME,
    CONF_POWER_THRESHOLD,
    CONF_UNTRACKED_ENERGY,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_SENSOR_PRECISION,
)
from custom_components.powercalc.device_binding import get_device_info

from custom_components.powercalc.sensors.abstract import (
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
)
from .energy import EnergySensor, get_unit_prefix
from custom_components.powercalc.sensors.power import PowerSensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

UNTRACKED_ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_POWER_THRESHOLD): vol.Coerce(float),
        vol.Required(CONF_MIN_TIME): cv.time_period,
    },
)

_LOGGER = logging.getLogger(__name__)


async def create_untracked_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
    source_entity: SourceEntity,
) -> UntrackedEnergySensor:
    """Create a virtual energy sensor using riemann integral integration."""
    name = generate_energy_sensor_name(
        sensor_config,
        sensor_config.get(CONF_NAME),
        source_entity,
    )
    unique_id = f"{power_sensor.unique_id}_energy" if power_sensor.unique_id is not None else None
    entity_id = generate_energy_sensor_entity_id(
        hass,
        sensor_config,
        source_entity,
        unique_id=unique_id,
    )
    unit_prefix = get_unit_prefix(hass, sensor_config, power_sensor)

    _LOGGER.debug(
        "Creating untracked energy sensor (entity_id=%s, source_entity=%s, unit_prefix=%s)",
        entity_id,
        power_sensor.entity_id,
        unit_prefix,
    )

    return UntrackedEnergySensor(
        source_entity=power_sensor.entity_id,
        unique_id=unique_id,
        entity_id=entity_id,
        name=name,
        unit_prefix=unit_prefix,
        sensor_config=sensor_config,
        device_info=get_device_info(hass, sensor_config, source_entity),
    )


class UntrackedEnergySensor(EnergySensor, RestoreSensor):
    """Untracked energy sensor, totalling kWh."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = ENERGY_ICON
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_should_poll = False

    def __init__(
        self,
        source_entity: str,
        entity_id: str,
        sensor_config: ConfigType,
        unique_id: str | None = None,
        name: str | None = None,
        unit_prefix: str | None = None,
        device_info: DeviceInfo | None = None,
    ) -> None:
        self._rounding_digits: int = int(sensor_config.get(CONF_ENERGY_SENSOR_PRECISION, DEFAULT_ENERGY_SENSOR_PRECISION))
        integration_method: str = sensor_config.get(CONF_ENERGY_INTEGRATION_METHOD, DEFAULT_ENERGY_INTEGRATION_METHOD)

        self._sensor_config = sensor_config
        self.entity_id = entity_id

        untracked_config: dict[str, Any] = sensor_config[CONF_UNTRACKED_ENERGY]
        self._power_threshold = Decimal(untracked_config[CONF_POWER_THRESHOLD])
        self._min_time: timedelta = untracked_config[CONF_MIN_TIME]

        self._source_entity = source_entity
        self._tracking_started_at: datetime | None = None
        self._seen_power_values: list[tuple[datetime, Decimal]] = []
        self._method = _IntegrationMethod.from_name(integration_method)
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR  # todo
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_suggested_display_precision = self._rounding_digits or DEFAULT_ENERGY_SENSOR_PRECISION

        self._unit_prefix = UNIT_PREFIXES[unit_prefix]
        self._unit_time = UNIT_TIME[UnitOfTime.HOURS]

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""

        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = Decimal(str(last_sensor_data.native_value))
            self._attr_native_unit_of_measurement = last_sensor_data.native_unit_of_measurement
        else:
            self._attr_native_value = Decimal(0)

        self.async_on_remove(start.async_at_start(self.hass, self.start_tracking))

    async def start_tracking(self, _: Any) -> None:  # noqa
        """Initialize tracking the source entity after HA has started."""

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._source_entity],
                self.on_state_change,
            ),
        )

    @callback
    def on_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Triggered when power sensor changes state."""
        new_state = event.data.get("new_state")
        if not new_state:  # pragma: no cover
            return

        current_power = Decimal(new_state.state)
        if not self.is_matching_condition(current_power):
            _LOGGER.debug("%s: Power does not exceed threshold", self.entity_id)
            self._tracking_started_at = None
            self._seen_power_values.clear()
            return

        if self._tracking_started_at is None:
            self._tracking_started_at = datetime.now(tz=UTC)

        current_time = datetime.now(tz=UTC)
        elapsed_time = current_time - self._tracking_started_at
        self._seen_power_values.append((current_time, current_power))

        if elapsed_time < self._min_time:
            _LOGGER.debug("%s: Min time not reached yet, elapsed: %s", self.entity_id, elapsed_time.seconds)
            return

        _LOGGER.debug("%s: Min time reached, calculate integration", self.entity_id)
        integration = self.calculate_integration()
        if not isinstance(self._attr_native_value, Decimal):
            self._attr_native_value = Decimal(0)
        self._attr_native_value += integration

        self.async_write_ha_state()

    def calculate_integration(self) -> Decimal:
        """Calculate the integration of the power values."""
        total_integration = Decimal(0)

        # Iterate over consecutive pairs of (time, power) values
        for (t1, p1), (t2, p2) in zip(self._seen_power_values, self._seen_power_values[1:], strict=False):
            elapsed = Decimal((t2 - t1).seconds)
            area = self._method.calculate_area_with_two_states(elapsed, p1, p2)
            scaled = area / (self._unit_prefix * self._unit_time)

            _LOGGER.debug(
                "%s: Integration between %s and %s: %s",
                self.entity_id,
                t1,
                t2,
                scaled,
            )

            total_integration += scaled

        return total_integration

    def is_matching_condition(self, power: Decimal) -> bool:
        """Check if the state matches the requirements."""
        return power > self._power_threshold

    @property
    def native_value(self) -> Decimal | None:  # type: ignore[override]
        """Return the state of the sensor."""
        if isinstance(self._attr_native_value, Decimal) and self._attr_native_value:
            return round(self._attr_native_value, self._rounding_digits)
        return self._attr_native_value  # type: ignore

    @callback
    def async_reset(self) -> None:
        _LOGGER.debug("%s: Reset energy sensor", self.entity_id)
        self._attr_native_value = 0
        self.async_write_ha_state()
