from homeassistant.components import light
from homeassistant.core import State
import logging

from homeassistant.components import fan
from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS
)
from homeassistant.components.fan import (
    ATTR_PERCENTAGE
)
from .strategy_interface import PowerCalculationStrategyInterface
from typing import Optional
import homeassistant.helpers.entity_registry as er

_LOGGER = logging.getLogger(__name__)

class LinearStrategy(PowerCalculationStrategyInterface):
    def __init__(self, min: float, max: float) -> None:
        self._min = float(min)
        self._max = float(max)
    
    async def calculate(self, entity_state: State) -> Optional[int]:
        attrs = entity_state.attributes

        if (entity_state.domain == light.DOMAIN):
            max_value = 255
            value = attrs.get(ATTR_BRIGHTNESS)
            if (value == None):
                _LOGGER.error("No brightness for entity: %s", entity_state.entity_id)
                return None
        
        if (entity_state.domain == fan.DOMAIN):
            max_value = 100
            value = attrs.get(ATTR_PERCENTAGE)
            if (value == None):
                _LOGGER.error("No percentage for entity: %s", entity_state.entity_id)
                return None

        converted = ( (value - 0) / (max_value - 0) ) * (self._max - self._min) + self._min
        return round(converted, 2)
    
    async def validate_config(self, entity_entry: er.RegistryEntry):
        """Validate correct setup of the strategy"""
        pass