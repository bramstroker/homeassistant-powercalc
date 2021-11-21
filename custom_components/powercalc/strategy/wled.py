from __future__ import annotations

from typing import Optional

import voluptuous as vol
from homeassistant.core import State

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.helpers import evaluate_power
from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("voltage"): vol.Coerce(float),
    }
)


class WledStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: dict
    ) -> None:
        self._power = 0

    async def calculate(self, entity_state: State) -> Optional[float]:
        return await evaluate_power(4)

    async def validate_config(self, source_entity: SourceEntity):
        """Validate correct setup of the strategy"""

        pass
