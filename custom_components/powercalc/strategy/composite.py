from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from homeassistant.const import CONF_ENTITY_ID, STATE_OFF
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.condition import ConditionCheckerType
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.template import Template

from .playbook import PlaybookStrategy
from .strategy_interface import PowerCalculationStrategyInterface

_LOGGER = logging.getLogger(__name__)


class CompositeStrategy(PowerCalculationStrategyInterface):
    def __init__(self, hass: HomeAssistant, strategies: list[SubStrategy]) -> None:
        self.hass = hass
        self.strategies = strategies
        self.playbook_strategies: list[PlaybookStrategy] = [
            strategy.strategy for strategy in self.strategies if isinstance(strategy.strategy, PlaybookStrategy)
        ]

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate power consumption based on entity state."""
        await self.stop_active_playbooks()

        for sub_strategy in self.strategies:
            strategy = sub_strategy.strategy

            if sub_strategy.condition and not sub_strategy.condition(self.hass, {"state": entity_state}):
                continue

            if isinstance(strategy, PlaybookStrategy):
                await self.activate_playbook(strategy)

            if entity_state.state == STATE_OFF and strategy.can_calculate_standby():
                return await strategy.calculate(entity_state)

            if entity_state.state != STATE_OFF:
                return await strategy.calculate(entity_state)

        return None

    async def stop_active_playbooks(self) -> None:
        """Stop any active playbooks from sub strategies."""
        for playbook in self.playbook_strategies:
            await playbook.stop_playbook()

    @staticmethod
    async def activate_playbook(strategy: PlaybookStrategy) -> None:
        """Activate the first playbook in the list."""
        if not strategy.registered_playbooks:
            return  # pragma: no cover
        playbook = strategy.registered_playbooks[0]
        await strategy.activate_playbook(playbook)

    def set_update_callback(self, update_callback: Callable[[Decimal], None]) -> None:
        """
        Register update callback which allows to give the strategy instance access to the power sensor
        and manipulate the state
        """
        for sub_strategy in self.strategies:
            if hasattr(sub_strategy.strategy, "set_update_callback"):
                sub_strategy.strategy.set_update_callback(update_callback)

    async def validate_config(self) -> None:
        """Validate correct setup of the strategy."""
        for sub_strategy in self.strategies:
            await sub_strategy.strategy.validate_config()

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        """Return entities that should be tracked."""
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
        """Resolve track templates from condition config."""
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
