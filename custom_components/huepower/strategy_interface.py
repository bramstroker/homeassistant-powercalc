from homeassistant.core import State
from typing import Optional

class PowerCalculationStrategyInterface:
    async def calculate(self, light_state: State) -> Optional[int]:
        """Calculate power consumption based on entity state"""
        pass