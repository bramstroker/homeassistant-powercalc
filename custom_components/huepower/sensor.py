"""Platform for sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
from .const import (
    DOMAIN,
    DATA_CALCULATOR,
    CONF_MODEL
)
from . import PowerCalculator
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er

from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    DEVICE_CLASS_POWER,
    POWER_WATT,
    STATE_UNKNOWN,
    CONF_NAME,
    CONF_ENTITY_ID
)
import voluptuous as vol

from homeassistant.components import light
from homeassistant.components.light import Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_domain(light.DOMAIN),
        vol.Optional(CONF_MODEL): cv.string
    }
)

NAME_FORMAT = "{} power"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the sensor platform."""

    power_calculator = hass.data[DOMAIN][DATA_CALCULATOR]

    entity_id = config[CONF_ENTITY_ID]

    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(entity_id)
    unique_id = entity_entry.unique_id

    light = await find_hue_light(hass, entity_id)
    if (light is None):
        _LOGGER.error("Cannot setup power sensor for light '%s', not found in the hue bridge api")
        return
        
    name = config.get(CONF_NAME)
    if (name == None):
        name = NAME_FORMAT.format(light.name)

    model = config.get(CONF_MODEL) or light.modelid

    async_add_entities([
        HuePowerSensor(
            power_calculator=power_calculator,
            name=name,
            entity_id=config[CONF_ENTITY_ID],
            unique_id=unique_id,
            manufacturer=light.manufacturername,
            light_model=model
        )
    ])

async def find_hue_light(hass, entity_id) -> Light | None:
    """Find the light in the Hue bridge, we need to extract the model id."""
    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(entity_id)
    unique_id = entity_entry.unique_id

    bridge = hass.data[HUE_DOMAIN][entity_entry.config_entry_id]
    lights = bridge.api.lights
    for light_id in lights:
        light = bridge.api.lights[light_id]
        if (light.uniqueid == unique_id):
            return light
    
    return None

class HuePowerSensor(Entity):
    """Representation of a Sensor."""

    def __init__(
        self,
        power_calculator: PowerCalculator,
        name: str,
        entity_id: str,
        manufacturer: str,
        light_model: str,
        unique_id: str,
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._state = None
        self._entity_id = entity_id
        self._name = name
        self._power = None
        self._manufacturer = manufacturer
        self._light_model = light_model
        self._unique_id = unique_id

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

        self._power = await self._power_calculator.calculate(
            self._manufacturer,
            self._light_model,
            light_state
        )

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
    def unique_id(self):
        """Return a unique id."""
        return self._unique_id

    @property
    def available(self):
        """Return True if entity is available."""
        return self._power is not None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return POWER_WATT
    
    @property
    def device_class(self) -> str:
        """Device class of the sensor."""
        return DEVICE_CLASS_POWER
