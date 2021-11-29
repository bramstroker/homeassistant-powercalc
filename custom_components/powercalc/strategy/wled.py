from __future__ import annotations

import logging
from typing import Optional

import voluptuous as vol
from homeassistant.core import State, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_POWER_FACTOR, CONF_VOLTAGE
from custom_components.powercalc.errors import (
    SensorConfigurationError,
    StrategyConfigurationError,
)
from custom_components.powercalc.helpers import evaluate_power

from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VOLTAGE): vol.Coerce(float),
        vol.Optional(CONF_POWER_FACTOR, default=0.9): vol.Coerce(float),
    }
)

_LOGGER = logging.getLogger(__name__)


class WledStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self, config: dict, light_entity: SourceEntity, hass: HomeAssistantType
    ) -> None:
        self._hass = hass
        self._voltage = config.get(CONF_VOLTAGE)
        self._power_factor = config.get(CONF_POWER_FACTOR) or 0.9
        self._light_entity = light_entity

    async def calculate(self, entity_state: State) -> Optional[float]:
        if entity_state.entity_id != self._estimated_current_entity:
            return None

        _LOGGER.debug(
            f"{self._light_entity.entity_id}: Estimated current {entity_state.state} (voltage={self._voltage}, power_factor={self._power_factor})"
        )
        power = float(entity_state.state) / 1000 * self._voltage * self._power_factor
        return await evaluate_power(power)

    async def find_estimated_current_entity(self) -> str:
        entity_reg = entity_registry.async_get(self._hass)
        entity_id = f"sensor.{self._light_entity.object_id}_estimated_current"
        entry = entity_reg.async_get(entity_id)
        if entry:
            return entry.entity_id

        device_id = self._light_entity.entity_entry.device_id
        estimated_current_entities = [
            entity_entry.entity_id
            for entity_entry in entity_registry.async_entries_for_device(
                entity_reg, device_id
            )
            if "estimated_current" in entity_entry.entity_id
        ]
        if estimated_current_entities:
            return estimated_current_entities[0]

        raise StrategyConfigurationError("{No estimated current entity found")

    def get_entities_to_track(self) -> tuple:
        return {self._estimated_current_entity}

    def can_calculate_standby(self) -> bool:
        return True

    async def validate_config(self, source_entity: SourceEntity):
        self._estimated_current_entity = await self.find_estimated_current_entity()
