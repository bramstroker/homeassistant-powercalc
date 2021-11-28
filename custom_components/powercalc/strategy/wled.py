from __future__ import annotations

import logging
from typing import Optional

import voluptuous as vol
from homeassistant.core import State

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_VOLTAGE, CONF_POWER_FACTOR
from custom_components.powercalc.helpers import evaluate_power
from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VOLTAGE): vol.Coerce(float),
        vol.Optional(CONF_POWER_FACTOR, default=0.9): vol.Coerce(float)
    }
)

_LOGGER = logging.getLogger(__name__)


class WledStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: dict,
        light_entity: SourceEntity
    ) -> None:
        self._voltage = config.get(CONF_VOLTAGE)
        self._power_factor = config.get(CONF_POWER_FACTOR) or 0.9
        self._light_entity = light_entity

        self._estimated_current_entity = f"sensor.{self._light_entity.object_id}_estimated_current"

    async def calculate(self, entity_state: State) -> Optional[float]:
        if entity_state.entity_id != self._estimated_current_entity:
            return None

        _LOGGER.debug(f"{self._light_entity.entity_id}: Estimated current {entity_state.state} (voltage={self._voltage}, power_factor={self._power_factor})")
        power = float(entity_state.state) / 1000 * self._voltage * self._power_factor
        return await evaluate_power(power)
    
    def get_entities_to_track(self) -> tuple:
        return {self._estimated_current_entity}
    
    def can_calculate_standby(self) -> bool:
        return True
