from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import condition

from .strategy_interface import PowerCalculationStrategyInterface

_LOGGER = logging.getLogger(__name__)


class CompositeStrategy(PowerCalculationStrategyInterface):
    def __init__(self, hass: HomeAssistant, strategies: list[SubStrategy]) -> None:
        self.hass = hass
        self.strategies = strategies

    async def calculate(self, entity_state: State) -> Decimal | None:
        for sub_strategy in self.strategies:

            cond = await condition.async_from_config(self.hass, sub_strategy.condition)
            check = cond(self.hass, {"state": entity_state})
            if not check:
                continue

            return await sub_strategy.strategy.calculate(entity_state)

        return None


@dataclass
class SubStrategy:
    condition: dict
    strategy: PowerCalculationStrategyInterface
