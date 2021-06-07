from homeassistant.core import State
from typing import Optional
from .strategy_interface import PowerCalculationStrategyInterface

class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(self, wattage) -> None:
        self._wattage = wattage
    
    async def calculate(self, light_state: State) -> Optional[int]:
        return self._wattage