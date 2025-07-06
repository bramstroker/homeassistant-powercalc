from __future__ import annotations

import logging
from decimal import Decimal

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_POWER_FACTOR,
    CONF_VOLTAGE,
    OFF_STATES,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.helpers import evaluate_power, get_related_entity_by_device_class

from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VOLTAGE): vol.Coerce(float),
        vol.Optional(CONF_POWER_FACTOR, default=0.9): vol.Coerce(float),
    },
)

_LOGGER = logging.getLogger(__name__)


class WledStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: ConfigType,
        light_entity: SourceEntity,
        hass: HomeAssistant,
        standby_power: float | None = None,
    ) -> None:
        self._hass = hass
        self._voltage = config.get(CONF_VOLTAGE) or 0
        self._power_factor = config.get(CONF_POWER_FACTOR) or 0.9
        self._light_entity = light_entity
        self._standby_power: Decimal = Decimal(standby_power or 0)
        self._estimated_current_entity: str | None = None

    async def calculate(self, entity_state: State) -> Decimal | None:
        light_state = entity_state if entity_state.entity_id == self._light_entity.entity_id else self._hass.states.get(self._light_entity.entity_id)

        if light_state.state in OFF_STATES and self._standby_power:
            return self._standby_power

        if entity_state.entity_id != self._estimated_current_entity:
            entity_state = self._hass.states.get(self._estimated_current_entity)

        if entity_state.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
            _LOGGER.warning(
                "%s: Estimated current entity %s is not available",
                self._light_entity.entity_id,
                self._estimated_current_entity,
            )
            return None

        _LOGGER.debug(
            "%s: Estimated current %s (voltage=%d, power_factor=%.2f)",
            self._light_entity.entity_id,
            entity_state.state,
            self._voltage,
            self._power_factor,
        )
        power = float(entity_state.state) / 1000 * self._voltage * self._power_factor
        return await evaluate_power(power)

    async def find_estimated_current_entity(self) -> str:
        entity_reg = entity_registry.async_get(self._hass)
        entity_id = f"sensor.{self._light_entity.object_id}_estimated_current"
        entry = entity_reg.async_get(entity_id)
        if entry:
            return entry.entity_id

        if self._light_entity.entity_entry:
            entity = get_related_entity_by_device_class(self._hass, self._light_entity.entity_entry, SensorDeviceClass.CURRENT)
            if entity:
                return entity

        raise StrategyConfigurationError("No estimated current entity found. Probably brightness limiter not enabled. See documentation")

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        if self._estimated_current_entity:
            return [self._estimated_current_entity]
        return []  # pragma: no cover

    def can_calculate_standby(self) -> bool:
        return True

    async def validate_config(self) -> None:
        self._estimated_current_entity = await self.find_estimated_current_entity()
