from __future__ import annotations

from typing import Optional

import voluptuous as vol
from homeassistant.core import State, split_entity_id

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_VOLTAGE
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.helpers import evaluate_power
from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VOLTAGE): vol.Coerce(float),
    }
)


class WledStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: dict,
        light_entity: SourceEntity
    ) -> None:
        self._voltage = config.get(CONF_VOLTAGE)
        self._light_entity = light_entity

        self._estimated_current_entity = f"sensor.{self._light_entity.object_id}_estimated_current"

    async def calculate(self, entity_state: State) -> Optional[float]:
        if entity_state.entity_id != self._estimated_current_entity:
            return None

        power = float(entity_state.state) / 1000 * self._voltage
        return await evaluate_power(power)
    
    def get_entities_to_track(self) -> tuple:
        return {self._estimated_current_entity}
