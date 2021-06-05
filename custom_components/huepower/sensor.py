"""Platform for sensor integration."""
from __future__ import annotations
from collections import defaultdict
import os;
from csv import reader
from functools import partial

from attr import attr
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.const import (
    ATTR_ENTITY_ID,
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
    ATTR_HS_COLOR,
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
    powerCalculator = PowerCalculator(hass)
    async_add_entities([
        HuePowerSensor(
            powerCalculator,
            config[CONF_NAME],
            config[CONF_ENTITY_ID]
        )
    ])

class HuePowerSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, power_calculator: PowerCalculator, name: str, entity_id: str):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._state = None
        self._entity_id = entity_id
        self._name = name
        self._power = None

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
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return POWER_WATT

class PowerCalculator:
    def __init__(self, hass) -> None:
        self._hass = hass
        self._lookup_dictionaries = {}

    async def calculate(self, light_state):
        """Calculate the power consumption based on brightness, mired, hsl values."""
        if (light_state.state == STATE_OFF):
            return 0

        entity_registry = await er.async_get_registry(self._hass)
        entity_entry = entity_registry.async_get(light_state.entity_id)
        device_registry = await dr.async_get_registry(self._hass)
        device_entry = device_registry.async_get(entity_entry.device_id)
        #@todo, calculate power consumption based on lookup tables with measurements
        attrs = light_state.attributes
        color_modes = attrs.get(light.ATTR_SUPPORTED_COLOR_MODES)

        brightness = attrs[ATTR_BRIGHTNESS]
        lookup_table = self.get_lookup_dictionary("")
        #lookup_table = self.get_lookup_table("", "")
        if light.color_supported(color_modes):
            hs = attrs[ATTR_HS_COLOR]
            hue = int(hs[0] / 360 * 65535) 
            sat = int(hs[1] / 100 * 255)
            hue_values = self.get_closest_from_dictionary(lookup_table, brightness)
            sat_values = self.get_closest_from_dictionary(hue_values, hue)
            power = self.get_closest_from_dictionary(sat_values, sat)
        else:
            mired = attrs[ATTR_COLOR_TEMP]
            mired_values = self.get_closest_from_dictionary(lookup_table, brightness)
            power = self.get_closest_from_dictionary(mired_values, mired)

        return power

    def get_closest_from_dictionary(self, dict, search_key):
        return dict.get(search_key) or dict[
            min(dict.keys(), key = lambda key: abs(key-search_key))
        ]

    def get_lookup_table(self, manufacturer: str, model: str):
        return {
            10: {
                10: 1.6,
                20: 1.8 
            },
            20: {
                10: 1.6,
                20: 1.8
            },
            60: {
                10: 1.6,
                20: 1.8,
                300: 2.9,
                310: 3.4,
                400: 5
            }
        }

    def get_lookup_dictionary(self, model: str):
        lookup_dict = self._lookup_dictionaries.get(model)
        if (lookup_dict == None):
            defaultdict_of_dict = partial(defaultdict, dict)
            lookup_dict = defaultdict(defaultdict_of_dict)
            #lookup_dict = defaultdict(dict)

            path = os.path.join(
                os.path.dirname(__file__),
                "data/test.csv"
            )

            with open(path, 'r') as csv_file:
                csv_reader = reader(csv_file)
                next(csv_reader)
                # Iterate over each row in the csv using reader object
                for row in csv_reader:
                    lookup_dict[int(row[0])][int(row[1])][int(row[2])] = float(row[3])

            lookup_dict = dict(lookup_dict)

        return lookup_dict