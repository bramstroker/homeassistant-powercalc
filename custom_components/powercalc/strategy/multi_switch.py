from __future__ import annotations

import logging
from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import CONF_ENTITIES, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import TrackTemplate

from custom_components.powercalc.const import CONF_POWER, CONF_POWER_OFF, DUMMY_ENTITY_ID

from .strategy_interface import PowerCalculationStrategyInterface

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_POWER_OFF): vol.Coerce(float),
        vol.Required(CONF_ENTITIES): cv.entities_domain(SWITCH_DOMAIN),
    },
)

_LOGGER = logging.getLogger(__name__)


class MultiSwitchStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        hass: HomeAssistant,
        switch_entities: list[str],
        on_power: Decimal,
        off_power: Decimal,
    ) -> None:
        self.hass = hass
        self.switch_entities = switch_entities
        self.known_states: dict[str, str] | None = None
        self.on_power = on_power
        self.off_power = off_power

    async def calculate(self, entity_state: State) -> Decimal | None:
        if self.known_states is None:
            self.known_states = {
                entity_id: (state.state if (state := self.hass.states.get(entity_id)) else STATE_UNAVAILABLE) for entity_id in self.switch_entities
            }

        if entity_state.entity_id != DUMMY_ENTITY_ID:
            self.known_states[entity_state.entity_id] = entity_state.state

        def _get_power(state: str) -> Decimal:
            if state == STATE_UNAVAILABLE:
                return Decimal(0)
            if state == STATE_ON:
                return self.on_power
            return self.off_power

        return Decimal(sum(_get_power(state) for state in self.known_states.values()))

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        return self.switch_entities  # type: ignore

    def can_calculate_standby(self) -> bool:
        return True
