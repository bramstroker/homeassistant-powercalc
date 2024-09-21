from __future__ import annotations

from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import climate, vacuum
from homeassistant.core import State
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.template import Template

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_POWER, CONF_STATES_POWER
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.helpers import evaluate_power

from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Any(vol.Coerce(float), cv.template),
        vol.Optional(CONF_STATES_POWER): vol.Schema(
            {cv.string: vol.Any(vol.Coerce(float), cv.template)},
        ),
    },
)

STATE_BASED_ENTITY_DOMAINS = [
    climate.DOMAIN,
    vacuum.DOMAIN,
]


class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        source_entity: SourceEntity,
        power: Template | float | None,
        per_state_power: dict[str, float | Template] | None,
    ) -> None:
        self._source_entity = source_entity
        self._power = power
        self._per_state_power = per_state_power

    async def calculate(self, entity_state: State) -> Decimal | None:
        if self._per_state_power is not None:
            # Lookup by state
            if entity_state.state in self._per_state_power:
                return await evaluate_power(
                    self._per_state_power.get(entity_state.state) or 0,
                )

            # Lookup by state attribute (attribute|value)
            for state_key, power in self._per_state_power.items():
                if "|" in state_key:
                    attribute, value = state_key.split("|", 2)
                    if str(entity_state.attributes.get(attribute)) == value:
                        return await evaluate_power(power)

        if self._power is None:
            return None

        return await evaluate_power(self._power)

    async def validate_config(self) -> None:
        """Validate correct setup of the strategy."""
        if self._power is None and self._per_state_power is None:
            raise StrategyConfigurationError(
                "You must supply one of 'states_power' or 'power'",
                "fixed_mandatory",
            )

        if self._source_entity.domain in STATE_BASED_ENTITY_DOMAINS and self._per_state_power is None:
            raise StrategyConfigurationError(
                "This entity can only work with 'states_power' not 'power'",
                "fixed_states_power_only",
            )

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        """Return entities that should be tracked."""
        track_templates: list[str | TrackTemplate] = []

        if isinstance(self._power, Template):
            track_templates.append(TrackTemplate(self._power, None, None))

        if self._per_state_power:
            for power in list(self._per_state_power.values()):
                if isinstance(power, Template):
                    track_templates.append(TrackTemplate(power, None, None))  # noqa: PERF401

        return track_templates
