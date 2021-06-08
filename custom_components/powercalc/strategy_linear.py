from homeassistant.core import State
import logging
from homeassistant.components.light import (
    ATTR_BRIGHTNESS
)
from .strategy_interface import PowerCalculationStrategyInterface
from typing import Optional
import homeassistant.helpers.entity_registry as er

_LOGGER = logging.getLogger(__name__)

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
    
    def validate_config(self, entity_entry: er.RegistryEntry):
        """Validate correct setup of the strategy"""
        pass