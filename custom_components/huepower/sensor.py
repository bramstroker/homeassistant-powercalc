"""Platform for sensor integration."""

from __future__ import annotations
from .const import (
    DOMAIN,
    DATA_CALCULATOR,
    CONF_MODEL
)
from . import PowerCalculator
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event

from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    POWER_WATT,
    STATE_UNKNOWN,
    CONF_NAME,
    CONF_ENTITY_ID
)
import voluptuous as vol

from homeassistant.components import light
from homeassistant.components.light import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

DEFAULT_NAME = "Hue power consumption"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_domain(light.DOMAIN),
        vol.Required(CONF_MODEL): cv.string
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the sensor platform."""

    power_calculator = hass.data[DOMAIN][DATA_CALCULATOR]
    async_add_entities([
        HuePowerSensor(
            power_calculator,
            config[CONF_NAME],
            config[CONF_ENTITY_ID],
            config[CONF_MODEL]
        )
    ])

class HuePowerSensor(Entity):
    """Representation of a Sensor."""

    def __init__(
        self,
        power_calculator: PowerCalculator,
        name: str,
        entity_id: str,
        light_model: str
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._state = None
        self._entity_id = entity_id
        self._name = name
        self._power = None
        self._light_model = light_model

    async def async_added_to_hass(self):
        """Register callbacks."""

        async def hue_light_state_listener(event):
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")

            await self._update_sensor(new_state)

        async def home_assistant_startup(event):
            """Add listeners and get initial state."""

            async_track_state_change_event(
                self.hass, [self._entity_id], hue_light_state_listener
            )

            light_state = self.hass.states.get(self._entity_id)

            await self._update_sensor(light_state)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, home_assistant_startup
        )

    async def _update_sensor(self, light_state):
        """Update power sensor based on new dependant hue light state."""
        if light_state is None:
            return False

        if light_state is None and light_state.state == STATE_UNKNOWN:
           return False

        self._power = await self._power_calculator.calculate(self._light_model, light_state)

        self.async_write_ha_state()
        return True

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

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return POWER_WATT
