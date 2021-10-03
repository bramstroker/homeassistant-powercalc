from __future__ import annotations

import logging

from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_INTEGRATION,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    DOMAIN,
)
from custom_components.powercalc.strategy_interface import (
    PowerCalculationStrategyInterface,
)
from homeassistant.core import callback
from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
)
from homeassistant.const import (
    DEVICE_CLASS_POWER,
    EVENT_HOMEASSISTANT_START,
    POWER_WATT,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

OFF_STATES = [STATE_OFF, STATE_NOT_HOME, STATE_STANDBY]

_LOGGER = logging.getLogger(__name__)


class VirtualPowerSensor(SensorEntity):
    """Virtual power sensor"""

    _attr_device_class = DEVICE_CLASS_POWER
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_unit_of_measurement = POWER_WATT

    def __init__(
        self,
        power_calculator: PowerCalculationStrategyInterface,
        calculation_mode: str,
        entity_id: str,
        name: str,
        source_entity: str,
        source_domain: str,
        unique_id: str,
        standby_power: float | None,
        scan_interval,
        multiply_factor: float | None,
        multiply_factor_standby: bool,
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._calculation_mode = calculation_mode
        self._source_entity = source_entity
        self._source_domain = source_domain
        self._name = name
        self._power = None
        self._standby_power = standby_power
        self._attr_force_update = True
        self._attr_unique_id = unique_id
        self._scan_interval = scan_interval
        self._multiply_factor = multiply_factor
        self._multiply_factor_standby = multiply_factor_standby
        self.entity_id = entity_id

    async def async_added_to_hass(self):
        """Register callbacks."""

        async def appliance_state_listener(event):
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")

            await self._update_power_sensor(new_state)

        async def home_assistant_startup(event):
            """Add listeners and get initial state."""

            async_track_state_change_event(
                self.hass, [self._source_entity], appliance_state_listener
            )

            new_state = self.hass.states.get(self._source_entity)

            await self._update_power_sensor(new_state)

        @callback
        def async_update(event_time=None):
            """Update the entity."""
            self.async_schedule_update_ha_state(True)

        async_track_time_interval(self.hass, async_update, self._scan_interval)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, home_assistant_startup
        )

    async def _update_power_sensor(self, state) -> bool:
        """Update power sensor based on new dependant hue light state."""
        if (
            state is None
            or state.state == STATE_UNKNOWN
            or state.state == STATE_UNAVAILABLE
        ):
            self._power = None
            self.async_write_ha_state()
            return False

        if state.state in OFF_STATES:
            self._power = self._standby_power or 0
            if self._multiply_factor and self._multiply_factor_standby:
                self._power *= self._multiply_factor
        else:
            self._power = await self._power_calculator.calculate(state)
            if self._multiply_factor and self._power is not None:
                self._power *= self._multiply_factor

        if self._power is None:
            self.async_write_ha_state()
            return False

        self._power = round(self._power, 2)

        _LOGGER.debug(
            'State changed to "%s" for entity "%s". Power:%s',
            state.state,
            state.entity_id,
            self._power,
        )

        self.async_write_ha_state()
        return True

    @property
    def extra_state_attributes(self):
        """Return entity state attributes."""
        return {
            ATTR_CALCULATION_MODE: self._calculation_mode,
            ATTR_INTEGRATION: DOMAIN,
            ATTR_SOURCE_ENTITY: self._source_entity,
            ATTR_SOURCE_DOMAIN: self._source_domain,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._power

    @property
    def available(self):
        """Return True if entity is available."""
        return self._power is not None
