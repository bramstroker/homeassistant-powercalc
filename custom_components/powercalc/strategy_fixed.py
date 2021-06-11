from homeassistant.core import State
from typing import Optional
from .strategy_interface import PowerCalculationStrategyInterface
import homeassistant.helpers.entity_registry as er

class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(self, wattage) -> None:
        self._wattage = wattage
    
    async def calculate(self, light_state: State) -> Optional[int]:
        return self._wattage
    
    async def validate_config(self, entity_entry: er.RegistryEntry):
        """Validate correct setup of the strategy"""
        pass