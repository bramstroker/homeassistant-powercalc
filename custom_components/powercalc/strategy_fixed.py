from typing import Optional

import homeassistant.helpers.entity_registry as er
from homeassistant.core import State

from .strategy_interface import PowerCalculationStrategyInterface


class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self, power: Optional[float], per_state_power: Optional[dict[str, float]]
    ) -> None:
        self._power = power
        self._per_state_power = per_state_power

    async def calculate(self, entity_state: State) -> Optional[int]:
        if entity_state.state in self._per_state_power:
            return self._per_state_power.get(entity_state.state)

        return self._power

    async def validate_config(self, entity_entry: er.RegistryEntry):
        """Validate correct setup of the strategy"""
        pass
