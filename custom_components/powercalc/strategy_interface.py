from homeassistant.core import State
from typing import Optional
import homeassistant.helpers.entity_registry as er

class PowerCalculationStrategyInterface:
    async def calculate(self, light_state: State) -> Optional[int]:
        """Calculate power consumption based on entity state"""
        pass

    async def validate_config(self, entity_entry: er.RegistryEntry):
        """Validate correct setup of the strategy"""
        pass