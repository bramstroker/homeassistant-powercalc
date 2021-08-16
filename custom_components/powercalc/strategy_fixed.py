from __future__ import annotations

from typing import Optional

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.core import State

from .const import CONF_POWER, CONF_STATES_POWER
from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_STATES_POWER, default={}): vol.Schema(
            {cv.string: vol.Coerce(float)}
        ),
    }
)


class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self, power: Optional[float], per_state_power: Optional[dict[str, float]]
    ) -> None:
        self._power = power
        self._per_state_power = per_state_power

    async def calculate(self, entity_state: State) -> Optional[int]:
        if self._per_state_power is not None:
            # Lookup by state
            if entity_state.state in self._per_state_power:
                return self._per_state_power.get(entity_state.state)
            else:
                # Lookup by state attribute (attribute|value)
                for state_key, power in self._per_state_power.items():
                    if "|" in state_key:
                        attribute, value = state_key.split("|", 2)
                        if entity_state.attributes.get(attribute) == value:
                            return power

        return self._power

    async def validate_config(self, entity_entry: er.RegistryEntry):
        """Validate correct setup of the strategy"""
        pass
