from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import climate, vacuum
from homeassistant.core import State
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
            {cv.string: vol.Any(vol.Coerce(float), cv.template)}
        ),
    }
)

STATE_BASED_ENTITY_DOMAINS = [
    climate.DOMAIN,
    vacuum.DOMAIN,
]


class FixedStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        power: Optional[Union[Template, float]],
        per_state_power: Optional[dict[str, float]],
    ) -> None:
        self._power = power
        self._per_state_power = per_state_power

    async def calculate(self, entity_state: State) -> Optional[Decimal]:
        if self._per_state_power is not None:
            # Lookup by state
            if entity_state.state in self._per_state_power:
                return await evaluate_power(
                    self._per_state_power.get(entity_state.state)
                )
            else:
                # Lookup by state attribute (attribute|value)
                for state_key, power in self._per_state_power.items():
                    if "|" in state_key:
                        attribute, value = state_key.split("|", 2)
                        if str(entity_state.attributes.get(attribute)) == value:
                            return await evaluate_power(power)

        if self._power is None:
            return None

        return await evaluate_power(self._power)

    async def validate_config(self, source_entity: SourceEntity):
        """Validate correct setup of the strategy"""

        if (
            source_entity.domain in STATE_BASED_ENTITY_DOMAINS
            and self._per_state_power is None
        ):
            raise StrategyConfigurationError(
                "This entity can only work with 'states_power' not 'power'"
            )
