"""The HuePower integration."""

from __future__ import annotations

from homeassistant.core import State
import logging

from typing import Optional
from collections import defaultdict
from homeassistant.helpers.config_validation import entity_id, key_dependency
import os;
from csv import reader
from functools import partial

from .const import (
    CONF_MODE,
    DOMAIN,
    DATA_CALCULATOR_FACTORY,
    MANUFACTURER_DIRECTORY_MAPPING,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT
)

from homeassistant.const import (
    STATE_OFF,
    STATE_UNAVAILABLE,
    CONF_MINIMUM,
    CONF_MAXIMUM
)
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
    hass.data[DOMAIN][DATA_CALCULATOR_FACTORY] = PowerCalculatorStrategyFactory(hass)

    return True

def get_light_model_directory(manufacturer: str, model: str) -> str:
    manufacturer_directory = MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer) or manufacturer

    return os.path.join(
        os.path.dirname(__file__),
        f'data/{manufacturer_directory}/{model}'
    )

class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(self, config: str, manufacturer: str, model: str) -> Optional[int]:
        mode = config.get(CONF_MODE) or MODE_LUT

        if (mode == MODE_LINEAR):
            return LinearStrategy(
                min=config.get(CONF_MINIMUM),
                max=config.get(CONF_MAXIMUM)
            )
        
        if (mode == MODE_FIXED):
            return FixedStrategy()
        
        if (mode == MODE_LUT):

            return LutStrategy(
                self._lut_registry,
                manufacturer=manufacturer,
                model=model
            )

class PowerCalculationStrategyInterface:
    async def calculate(self, light_state: State) -> Optional[int]:
        """Calculate power consumption based on entity state"""
        pass

class LutRegistry:
    def __init__(self) -> None:
        self._lookup_dictionaries = {}
    
    async def get_lookup_dictionary(self, manufacturer: str, model: str, color_mode: str):
        cache_key = f'{manufacturer}_{model}_{color_mode}'
        lookup_dict = self._lookup_dictionaries.get(cache_key)
        if (lookup_dict == None):
            defaultdict_of_dict = partial(defaultdict, dict)
            lookup_dict = defaultdict(defaultdict_of_dict)

            path = os.path.join(
                get_light_model_directory(manufacturer, model),
                f'{color_mode}.csv'
            )

            _LOGGER.debug("Loading data file: %s", path)

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
        
class LutStrategy(PowerCalculationStrategyInterface):
    def __init__(self, lut_registry: LutRegistry, manufacturer: str, model: str) -> None:
        self._lut_registry = lut_registry
        self._manufacturer = manufacturer
        self._model = model

    async def calculate(self, light_state: State) -> Optional[int]:
        """Calculate the power consumption based on brightness, mired, hsl values."""
        attrs = light_state.attributes
        color_mode = attrs.get(ATTR_COLOR_MODE)
        brightness = attrs.get(ATTR_BRIGHTNESS)
        if (brightness == None):
            _LOGGER.error("No brightness for entity: %s", light_state.entity_id)
            return None

        lookup_table = await self._lut_registry.get_lookup_dictionary(self._manufacturer, self._model, color_mode)
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
    
class LinearStrategy(PowerCalculationStrategyInterface):
    def __init__(self, min: float, max: float) -> None:
        self._min = float(min)
        self._max = float(max)
    
    async def calculate(self, light_state: State) -> Optional[int]:
        attrs = light_state.attributes
        brightness = attrs.get(ATTR_BRIGHTNESS)
        if (brightness == None):
            _LOGGER.error("No brightness for entity: %s", light_state.entity_id)
            return None

        converted = ( (brightness - 0) / (255 - 0) ) * (self._max - self._min) + self._min
        return round(converted, 2)

class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(self, wattage) -> None:
        self._wattage = wattage
    
    async def calculate(self, light_state: State) -> Optional[int]:
        return self._wattage