from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import logging
from typing import Any

from homeassistant.const import CONF_ATTRIBUTE, CONF_CONDITION, CONF_ENTITY_ID, STATE_OFF
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.condition import ConditionCheckerType
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.template import Template
import voluptuous as vol

from custom_components.powercalc.const import CONF_FIXED, CONF_LINEAR, CONF_MODE, CONF_MULTI_SWITCH, CONF_PLAYBOOK, CONF_STRATEGIES, CONF_WLED
from custom_components.powercalc.strategy.fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from custom_components.powercalc.strategy.linear import CONFIG_SCHEMA as LINEAR_SCHEMA
from custom_components.powercalc.strategy.multi_switch import CONFIG_SCHEMA as MULTI_SWITCH_SCHEMA
from custom_components.powercalc.strategy.playbook import CONFIG_SCHEMA as PLAYBOOK_SCHEMA, PlaybookStrategy
from custom_components.powercalc.strategy.strategy_interface import PowerCalculationStrategyInterface
from custom_components.powercalc.strategy.wled import CONFIG_SCHEMA as WLED_SCHEMA

_LOGGER = logging.getLogger(__name__)


class CompositeMode(StrEnum):
    STOP_AT_FIRST = "stop_at_first"
    SUM_ALL = "sum_all"


DEFAULT_MODE = CompositeMode.STOP_AT_FIRST


def make_entity_id_optional(schema: vol.Schema) -> vol.Schema:
    """Make entity_id optional in schema."""
    schema = schema.schema
    schema[vol.Optional(CONF_ENTITY_ID)] = schema.pop(vol.Required(CONF_ENTITY_ID))  # type: ignore
    return vol.Schema(schema)


def get_numeric_state_schema() -> vol.Schema:
    """Return the numeric state condition schema. We need to modify it to make entity_id optional."""
    return make_entity_id_optional(cv.NUMERIC_STATE_CONDITION_SCHEMA.validators[0])


def get_state_condition_attribute_schema(value: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return the state attribute condition schema. We need to modify it to make entity_id optional."""
    return make_entity_id_optional(cv.STATE_CONDITION_ATTRIBUTE_SCHEMA)(value)  # type: ignore


def get_state_condition_state_schema(value: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return the state condition schema. We need to modify it to make entity_id optional."""
    return make_entity_id_optional(cv.STATE_CONDITION_STATE_SCHEMA)(value)  # type: ignore


def get_state_schema(value: Any) -> dict[str, Any]:  # noqa: ANN401
    """Validate a state condition."""
    if not isinstance(value, dict):
        raise vol.Invalid("Expected a dictionary")  # pragma: no cover

    if CONF_ATTRIBUTE in value:
        validated: dict[str, Any] = get_state_condition_attribute_schema(value)
    else:
        validated = get_state_condition_state_schema(value)

    return cv.key_dependency("for", "state")(validated)


CONDITION_SCHEMA: vol.Schema = vol.Schema(
    vol.Any(
        vol.All(
            cv.expand_condition_shorthand,
            cv.key_value_schemas(
                CONF_CONDITION,
                {
                    "and": cv.AND_CONDITION_SCHEMA,
                    "device": cv.DEVICE_CONDITION_SCHEMA,
                    "not": cv.NOT_CONDITION_SCHEMA,
                    "numeric_state": get_numeric_state_schema(),
                    "or": cv.OR_CONDITION_SCHEMA,
                    "state": get_state_schema,
                    "template": cv.TEMPLATE_CONDITION_SCHEMA,
                },
            ),
        ),
        cv.dynamic_template_condition_action,
    ),
)

ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONDITION): CONDITION_SCHEMA,
        vol.Optional(CONF_FIXED): FIXED_SCHEMA,
        vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
        vol.Optional(CONF_WLED): WLED_SCHEMA,
        vol.Optional(CONF_PLAYBOOK): PLAYBOOK_SCHEMA,
        vol.Optional(CONF_MULTI_SWITCH): MULTI_SWITCH_SCHEMA,
    },
)

CONFIG_SCHEMA = vol.Any(
    vol.All(
        cv.ensure_list,
        [
            ITEM_SCHEMA,
        ],
    ),
    vol.Schema(
        {
            vol.Optional(CONF_MODE, default=DEFAULT_MODE): vol.In([cls.value for cls in CompositeMode]),
            vol.Optional(CONF_STRATEGIES): vol.All(
                cv.ensure_list,
                [
                    ITEM_SCHEMA,
                ],
            ),
        },
    ),
)


class CompositeStrategy(PowerCalculationStrategyInterface):
    def __init__(self, hass: HomeAssistant, strategies: list[SubStrategy], mode: CompositeMode) -> None:
        self.hass = hass
        self.strategies = strategies
        self.mode = mode
        self.playbook_strategies: list[PlaybookStrategy] = [
            strategy.strategy for strategy in self.strategies if isinstance(strategy.strategy, PlaybookStrategy)
        ]

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate power consumption based on entity state."""
        await self.stop_active_playbooks()

        total = Decimal(0)
        for sub_strategy in self.strategies:
            strategy = sub_strategy.strategy

            if sub_strategy.condition and not sub_strategy.condition(self.hass, {"state": entity_state}):
                continue

            if isinstance(strategy, PlaybookStrategy):
                await self.activate_playbook(strategy)

            if (entity_state.state == STATE_OFF and strategy.can_calculate_standby()) or entity_state.state != STATE_OFF:
                value = await strategy.calculate(entity_state)
                if value is not None:
                    if self.mode == CompositeMode.STOP_AT_FIRST:
                        return value
                    total += value

        return total if self.mode == CompositeMode.SUM_ALL else None

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

        track_entities = [entity for sub_strategy in self.strategies for entity in sub_strategy.strategy.get_entities_to_track()]
        return track_templates + track_entities

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
