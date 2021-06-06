"""The HuePower integration."""

from homeassistant.core import State
import logging

from typing import Optional
from collections import defaultdict
from homeassistant.helpers.config_validation import entity_id, key_dependency
import os;
from csv import reader
from functools import partial

from .const import (
    DOMAIN,
    DATA_CALCULATOR,
    MANUFACTURER_DIRECTORY_MAPPING
)

from homeassistant.const import (
    STATE_OFF,
    STATE_UNAVAILABLE
)
from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_MODE,
    ATTR_HS_COLOR,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS
)
from homeassistant.helpers.typing import HomeAssistantType

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_CALCULATOR] = PowerCalculator(hass)

    return True

class PowerCalculator:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lookup_dictionaries = {}

    async def calculate(self, manufacturer: str, model: str, light_state: State) -> Optional[int]:
        """Calculate the power consumption based on brightness, mired, hsl values."""
        if (light_state.state == STATE_OFF or light_state.state == STATE_UNAVAILABLE):
            return 0

        attrs = light_state.attributes
        color_mode = attrs.get(ATTR_COLOR_MODE)
        brightness = attrs.get(ATTR_BRIGHTNESS)
        if (brightness == None):
            _LOGGER.error("No brightness for entity: %s", light_state.entity_id)
            return None

        lookup_table = await self.get_lookup_dictionary(manufacturer, model, color_mode)
        if (lookup_table == None):
            _LOGGER.error("Lookup table not found")
            return None

        power = 0
        if (color_mode == COLOR_MODE_HS):
            hs = attrs[ATTR_HS_COLOR]
            hue = int(hs[0] / 360 * 65535) 
            sat = int(hs[1] / 100 * 255)
            _LOGGER.debug("Looking up power usage for bri:%s hue:%s sat:%s}", brightness, hue, sat)
            hue_values = self.get_closest_from_dictionary(lookup_table, brightness)
            sat_values = self.get_closest_from_dictionary(hue_values, hue)
            power = self.get_closest_from_dictionary(sat_values, sat)
        elif (color_mode == COLOR_MODE_COLOR_TEMP):
            mired = attrs[ATTR_COLOR_TEMP]
            _LOGGER.debug("Looking up power usage for bri:%s mired:%s", brightness, mired)
            mired_values = self.get_closest_from_dictionary(lookup_table, brightness)
            power = self.get_closest_from_dictionary(mired_values, mired)

        _LOGGER.debug("Power:%s", power)
        return power

    def get_closest_from_dictionary(self, dict: dict, search_key):
        return dict.get(search_key) or dict[
            min(dict.keys(), key = lambda key: abs(key-search_key))
        ]

    def get_light_model_directory(self, manufacturer: str, model: str) -> str:
        manufacturer_directory = MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer) or manufacturer

        return os.path.join(
            os.path.dirname(__file__),
            f'data/{manufacturer_directory}/{model}'
        )

    async def get_lookup_dictionary(self, manufacturer: str, model: str, color_mode: str):
        cache_key = f'{manufacturer}_{model}_{color_mode}'
        lookup_dict = self._lookup_dictionaries.get(cache_key)
        if (lookup_dict == None):
            defaultdict_of_dict = partial(defaultdict, dict)
            lookup_dict = defaultdict(defaultdict_of_dict)

            path = os.path.join(
                self.get_light_model_directory(manufacturer, model),
                f'{color_mode}.csv'
            )

            if (not os.path.exists(path)):
                _LOGGER.error("Data file not found: %s", path)
                return None

            with open(path, 'r') as csv_file:
                csv_reader = reader(csv_file)
                next(csv_reader) #skip header row

                for row in csv_reader:
                    if (color_mode == COLOR_MODE_HS):
                        lookup_dict[int(row[0])][int(row[1])][int(row[2])] = float(row[3])
                    else:
                        lookup_dict[int(row[0])][int(row[1])] = float(row[2])

            lookup_dict = dict(lookup_dict)
            self._lookup_dictionaries[cache_key] = lookup_dict

        return lookup_dict