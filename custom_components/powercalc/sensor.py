"""Platform for sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
from .const import (
    DOMAIN,
    DATA_CALCULATOR_FACTORY,
    CONF_MODEL,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MIN_WATT,
    CONF_MAX_WATT,
    CONF_WATT,
    CONF_STANDBY_USAGE,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT
)

from .strategy_interface import PowerCalculationStrategyInterface
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.event import async_track_state_change_event
import homeassistant.helpers.entity_registry as er

from homeassistant.const import (
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
from .errors import (
    ModelNotSupported,
    StrategyConfigurationError,
    UnsupportedMode
)
from .light_model import LightModel

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
        vol.Optional(CONF_MIN_WATT): cv.string,
        vol.Optional(CONF_MAX_WATT): cv.string,
        vol.Optional(CONF_WATT): cv.string,
        vol.Optional(CONF_STANDBY_USAGE): cv.string
    }
)

NAME_FORMAT = "{} power"


async def async_setup_platform(hass: HomeAssistantType, config, async_add_entities, discovery_info=None):
    """Set up the sensor platform."""

    calculation_strategy_factory = hass.data[DOMAIN][DATA_CALCULATOR_FACTORY]

    entity_id = config[CONF_ENTITY_ID]

    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(entity_id)

    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)

    entity_name = entity_entry.name or entity_entry.original_name
    name = config.get(CONF_NAME) or NAME_FORMAT.format(entity_name)

    if (manufacturer is None or model is None):
        hue_model_data = await autodiscover_hue_model(hass, entity_entry)
        if (hue_model_data):
            manufacturer = hue_model_data["manufacturer"]
            model = hue_model_data["model"]

    try:
        light_model = None
        if (manufacturer is not None and model is not None):
            light_model = LightModel(manufacturer, model)
        calculation_strategy = calculation_strategy_factory.create(config, light_model)
        await calculation_strategy.validate_config(entity_entry)
    except (ModelNotSupported, UnsupportedMode) as err:
        _LOGGER.error("Skipping sensor setup: %s", err)
        return
    except StrategyConfigurationError as err:
        _LOGGER.error("Error setting up calculation strategy: %s", err)
        return

    standby_usage = config.get(CONF_STANDBY_USAGE)
    if (standby_usage is None and light_model is not None):
        standby_usage = light_model.standby_usage

    _LOGGER.debug(
        "Setting up power sensor. entity_id:%s sensor_name:%s strategy=%s manufacturer=%s model=%s standby_usage=%s",
        entity_id,
        name,
        calculation_strategy.__class__.__name__,
        manufacturer,
        model,
        standby_usage
    )

    async_add_entities([
        GenericPowerSensor(
            power_calculator=calculation_strategy,
            name=name,
            entity_id=entity_id,
            unique_id=entity_entry.unique_id,
            standby_usage=standby_usage
        )
    ])

async def autodiscover_hue_model(hass, entity_entry):
    # When Philips Hue model is enabled we can auto discover manufacturer and model from the bridge data
    if (hass.data.get(HUE_DOMAIN) == None):
        return

    light = await find_hue_light(hass, entity_entry)
    if (light is None):
        _LOGGER.error("Cannot autodisover model for '%s', not found in the hue bridge api", entity_entry.entity_id)
        return

    _LOGGER.debug(
        "%s: (manufacturer=%s, model=%s)",
        entity_entry.entity_id,
        light.manufacturername,
        light.modelid
    )

    return {
        "manufacturer": light.manufacturername,
        "model": light.modelid
    }

async def find_hue_light(hass: HomeAssistantType, entity_entry: er.RegistryEntry) -> Light | None:
    """Find the light in the Hue bridge, we need to extract the model id."""

    bridge = hass.data[HUE_DOMAIN][entity_entry.config_entry_id]
    lights = bridge.api.lights
    for light_id in lights:
        light = bridge.api.lights[light_id]
        if (light.uniqueid == entity_entry.unique_id):
            return light
    
    return None

class GenericPowerSensor(Entity):
    """Representation of a Sensor."""

    def __init__(
        self,
        power_calculator: PowerCalculationStrategyInterface,
        name: str,
        entity_id: str,
        unique_id: str,
        standby_usage: float | None
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._entity_id = entity_id
        self._name = name
        self._power = None
        self._unique_id = unique_id
        self._standby_usage = standby_usage

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
        if light_state is None or light_state.state == STATE_UNKNOWN:
            return False

        if (light_state.state == STATE_UNAVAILABLE):
            return False

        if (light_state.state == STATE_OFF):
            self._power = self._standby_usage or 0
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
