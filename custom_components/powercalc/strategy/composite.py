from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.condition import ConditionCheckerType
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.template import Template

from .strategy_interface import PowerCalculationStrategyInterface

_LOGGER = logging.getLogger(__name__)


class CompositeStrategy(PowerCalculationStrategyInterface):
    def __init__(self, hass: HomeAssistant, strategies: list[SubStrategy]) -> None:
        self.hass = hass
        self.strategies = strategies

    async def calculate(self, entity_state: State) -> Decimal | None:
        for sub_strategy in self.strategies:
            if sub_strategy.condition and not sub_strategy.condition(
                self.hass,
                {"state": entity_state},
            ):
                continue

            return await sub_strategy.strategy.calculate(entity_state)

        return None

    async def validate_config(self) -> None:
        """Validate correct setup of the strategy."""
        for sub_strategy in self.strategies:
            await sub_strategy.strategy.validate_config()

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        track_templates: list[str | TrackTemplate] = []
        for sub_strategy in self.strategies:
            if sub_strategy.condition_config:
                self.resolve_track_templates_from_condition(
                    sub_strategy.condition_config,
                    track_templates,
                )
        return track_templates

    def can_calculate_standby(self) -> bool:
        """Return if this strategy can calculate standby power."""
        return any(sub_strategy.strategy.can_calculate_standby() for sub_strategy in self.strategies)

    async def on_start(self, hass: HomeAssistant) -> None:
        """Called after HA has started"""
        for sub_strategy in self.strategies:
            await sub_strategy.strategy.on_start(hass)

    def resolve_track_templates_from_condition(
        self,
        condition_config: dict,
        templates: list[str | TrackTemplate],
    ) -> None:
        for key, value in condition_config.items():
            if key == CONF_ENTITY_ID and isinstance(value, list):
                templates.extend(value)
            if isinstance(value, Template):
                templates.append(TrackTemplate(value, None, None))
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self.resolve_track_templates_from_condition(item, templates)


@dataclass
class SubStrategy:
    condition_config: dict | None
    condition: ConditionCheckerType | None
    strategy: PowerCalculationStrategyInterface
