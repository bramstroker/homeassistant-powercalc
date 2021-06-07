"""Platform for sensor integration."""

from __future__ import annotations

import logging
import os;

from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
from .const import (
    DOMAIN,
    DATA_CALCULATOR_FACTORY,
    CONF_MODEL,
    CONF_MANUFACTURER,
    CONF_MODE,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT
)
from . import PowerCalculationStrategyInterface
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
import homeassistant.helpers.entity_registry as er

from homeassistant.const import (
    CONF_MAXIMUM,
    CONF_MINIMUM,
    EVENT_HOMEASSISTANT_START,
    DEVICE_CLASS_POWER,
    POWER_WATT,
    STATE_UNKNOWN,
    CONF_NAME,
    CONF_ENTITY_ID,
    STATE_OFF,
    STATE_UNAVAILABLE
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
        vol.Optional(CONF_MODEL): cv.string,
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_MODE, default=MODE_LUT): vol.In(
            [
                MODE_LUT,
                MODE_FIXED,
                MODE_LINEAR
            ]
        ),
        vol.Optional(CONF_MINIMUM): cv.string,
        vol.Optional(CONF_MAXIMUM): cv.string
    }
)

NAME_FORMAT = "{} power"

class LightNotSupported(HomeAssistantError):
    """Raised when try to login as invalid user."""

async def async_setup_platform(hass: HomeAssistantType, config, async_add_entities, discovery_info=None):
    """Set up the sensor platform."""

    power_calculator_strategy = hass.data[DOMAIN][DATA_CALCULATOR_FACTORY]

    entity_id = config[CONF_ENTITY_ID]

    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(entity_id)

    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)

    # When Philips Hue model is enabled we can auto discover manufacturer and model from the bridge data
    if (hass.data.get(HUE_DOMAIN)):
        light = await find_hue_light(hass, entity_entry)
        if (light is None):
            _LOGGER.error("Cannot setup power sensor for light '%s', not found in the hue bridge api")
            return

        _LOGGER.debug(
            "%s: (manufacturer=%s, model=%s)",
            entity_id,
            light.manufacturername,
            light.modelid
        )

        if (manufacturer == None):
            manufacturer = light.manufacturername

        if (model == None):
            model = light.modelid

    if (manufacturer is None):
        _LOGGER.error("Manufacturer not supplied for entity: %s", entity_id)

    if (model is None):
        _LOGGER.error("Model not supplied for entity: %s", entity_id)
        return

    light_name = entity_entry.name or entity_entry.original_name
    name = config.get(CONF_NAME) or NAME_FORMAT.format(light_name)

    calculation_strategy = power_calculator_strategy.create(config, manufacturer, model)

    # try:
    #     validate_light_support(power_calculator, entity_entry, manufacturer, model)
    # except LightNotSupported as err:
    #     _LOGGER.error(
    #         "Light not supported: %s",
    #         err
    #     )
    #     return

    async_add_entities([
        HuePowerSensor(
            power_calculator=calculation_strategy,
            name=name,
            entity_id=config[CONF_ENTITY_ID],
            unique_id=entity_entry.unique_id,
            manufacturer=manufacturer,
            light_model=model
        )
    ])

async def find_hue_light(hass: HomeAssistantType, entity_entry: er.RegistryEntry) -> Light | None:
    """Find the light in the Hue bridge, we need to extract the model id."""

    bridge = hass.data[HUE_DOMAIN][entity_entry.config_entry_id]
    lights = bridge.api.lights
    for light_id in lights:
        light = bridge.api.lights[light_id]
        if (light.uniqueid == entity_entry.unique_id):
            return light
    
    return None

def validate_light_support(
    power_calculator: PowerCalculationStrategyInterface,
    entity_entry: er.RegistryEntry,
    manufacturer: str,
    model: str
):
    model_directory = power_calculator.get_light_model_directory(manufacturer, model)
    if (not os.path.exists(model_directory)):
        raise LightNotSupported("Model not found in data directory", model)
    
    supported_color_modes = entity_entry.capabilities['supported_color_modes']
    for mode in supported_color_modes:
        lookup_file = os.path.join(
            model_directory,
            f'{mode}.csv'
        )
        if (not os.path.exists(lookup_file)):
            raise LightNotSupported("No lookup file found for mode", mode)

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

        if (light_state.state == STATE_OFF or light_state.state == STATE_UNAVAILABLE):
            self._power = 0 #todo standy usage configurable
        else:
            self._power = await self._power_calculator.calculate(light_state)

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
