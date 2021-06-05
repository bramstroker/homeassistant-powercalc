"""The HuePower integration."""

from collections import defaultdict
from homeassistant.helpers.config_validation import key_dependency
import os;
from csv import reader
from functools import partial

from .const import (
    DOMAIN,
    DATA_CALCULATOR,
    MANUFACTURER_DIRECTORY_MAPPING
)

from homeassistant.const import (
    STATE_OFF
)
from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS
)
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import HomeAssistantType

async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_CALCULATOR] = PowerCalculator(hass)

    return True

class PowerCalculator:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lookup_dictionaries = {}

    async def calculate(self, model, light_state) -> int:
        """Calculate the power consumption based on brightness, mired, hsl values."""
        if (light_state.state == STATE_OFF):
            return 0

        entity_registry = await er.async_get_registry(self._hass)
        entity_entry = entity_registry.async_get(light_state.entity_id)
        device_registry = await dr.async_get_registry(self._hass)
        device_entry = device_registry.async_get(entity_entry.device_id)
        manufacturer = device_entry.manufacturer

        attrs = light_state.attributes
        color_modes = attrs.get(light.ATTR_SUPPORTED_COLOR_MODES)
        color_mode = attrs.get(light.ATTR_COLOR_MODE)

        brightness = attrs[ATTR_BRIGHTNESS]
        lookup_table = await self.get_lookup_dictionary(manufacturer, model, color_mode)
        if (lookup_table == None):
            #todo, what to do when no file exists for the given model?
            return 0

        #if light.color_supported(color_modes):
        power = 0
        if (color_mode == COLOR_MODE_HS):
            hs = attrs[ATTR_HS_COLOR]
            hue = int(hs[0] / 360 * 65535) 
            sat = int(hs[1] / 100 * 255)
            hue_values = self.get_closest_from_dictionary(lookup_table, brightness)
            sat_values = self.get_closest_from_dictionary(hue_values, hue)
            power = self.get_closest_from_dictionary(sat_values, sat)
        elif (color_mode == COLOR_MODE_COLOR_TEMP):
            mired = attrs[ATTR_COLOR_TEMP]
            mired_values = self.get_closest_from_dictionary(lookup_table, brightness)
            power = self.get_closest_from_dictionary(mired_values, mired)

        return power

    def get_closest_from_dictionary(self, dict, search_key):
        return dict.get(search_key) or dict[
            min(dict.keys(), key = lambda key: abs(key-search_key))
        ]

    async def get_lookup_dictionary(self, manufacturer: str, model: str, color_mode: str):
        key = f'{model}_{color_mode}'
        lookup_dict = self._lookup_dictionaries.get(key)
        if (lookup_dict == None):
            defaultdict_of_dict = partial(defaultdict, dict)
            lookup_dict = defaultdict(defaultdict_of_dict)
            
            manufacturer_directory = MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer)
            if (manufacturer_directory == None):
                #@todo log
                return None

            path = os.path.join(
                os.path.dirname(__file__),
                f'data/{manufacturer_directory}/{key}.csv'
            )

            if (not os.path.exists(path)):
                #@todo log
                return None

            with open(path, 'r') as csv_file:
                csv_reader = reader(csv_file)
                next(csv_reader) #skip header row

                for row in csv_reader:
                    lookup_dict[int(row[0])][int(row[1])][int(row[2])] = float(row[3])

            lookup_dict = dict(lookup_dict)
            self._lookup_dictionaries[key] = lookup_dict

        return lookup_dict