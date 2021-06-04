"""Platform for sensor integration."""
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    POWER_WATT,
    STATE_OFF,
    STATE_UNKNOWN,
    STATE_OFF,
    CONF_NAME,
    CONF_ENTITY_ID
)
import voluptuous as vol

from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    PLATFORM_SCHEMA
)
import homeassistant.helpers.config_validation as cv

DEFAULT_NAME = "Hue power consumption"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_domain(light.DOMAIN),
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the sensor platform."""
    async_add_entities([HuePowerSensor(config[CONF_NAME], config[CONF_ENTITY_ID])])

class HuePowerSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, name: str, entity_id: str):
        """Initialize the sensor."""
        self._state = None
        self._entity_id = entity_id
        self._name = name
        self._power = None

    async def async_added_to_hass(self):
        """Register callbacks."""

        @callback
        def hue_light_state_listener(event):
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")

            if self._update_sensor(new_state):
                 self.async_schedule_update_ha_state(True)

        @callback
        def home_assistant_startup(event):
            """Add listeners and get 1st state."""

            async_track_state_change_event(
                self.hass, [self._entity_id], hue_light_state_listener
            )

            light_state = self.hass.states.get(self._entity_id)

            if self._update_sensor(light_state):
                 self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, home_assistant_startup
        )

    def _update_sensor(self, light_state):
        """Update information based on new sensor states."""
        if light_state is None:
            return False

        if light_state is None and light_state.state == STATE_UNKNOWN:
           return False

        self._power = self._calculate_power_consumption(light_state=light_state)

        return True

    def _calculate_power_consumption(self, light_state):
        if (light_state.state == STATE_OFF):
            return 0

        #@todo, calculate power consumption based on lookup tables with measurements

        brightness = light_state.attributes[ATTR_BRIGHTNESS]
        mired = light_state.attributes[ATTR_COLOR_TEMP]
        power = brightness
        return power

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._power

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return POWER_WATT