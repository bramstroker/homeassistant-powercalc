from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from homeassistant.core import State

from .strategy_interface import PowerCalculationStrategyInterface

_LOGGER = logging.getLogger(__name__)


class CompositeStrategy(PowerCalculationStrategyInterface):
    def __init__(self, strategies: list[SubStrategy]) -> None:
        self.strategies = strategies

    async def calculate(self, entity_state: State) -> Decimal | None:
        for sub_strategy in self.strategies:
            # todo condition
            return await sub_strategy.strategy.calculate(entity_state)
        return None


@dataclass
class SubStrategy:
    condition: str
    strategy: PowerCalculationStrategyInterface
