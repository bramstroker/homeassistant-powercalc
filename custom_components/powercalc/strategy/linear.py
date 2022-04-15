from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import fan, light
from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.core import State
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_GAMMA_CURVE,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
)
from custom_components.powercalc.errors import StrategyConfigurationError

from .strategy_interface import PowerCalculationStrategyInterface

ALLOWED_DOMAINS = [fan.DOMAIN, light.DOMAIN]
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CALIBRATE): vol.All(
            cv.ensure_list, [vol.Match("^[0-9]+ -> ([0-9]*[.])?[0-9]+$")]
        ),
        vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
        vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
        vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
    }
)

_LOGGER = logging.getLogger(__name__)


class LinearStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: dict,
        hass: HomeAssistantType,
        source_entity: SourceEntity,
        standby_power: Optional[float],
    ) -> None:
        self._config = config
        self._hass = hass
        self._source_entity = source_entity
        self._standby_power = standby_power
        self._calibration = self.create_calibrate_list()

    async def calculate(self, entity_state: State) -> Optional[Decimal]:
        """Calculate the current power consumption"""
        value = self.get_current_state_value(entity_state)

        min_calibrate = self.get_min_calibrate(value)
        max_calibrate = self.get_max_calibrate(value)
        min_value = min_calibrate[0]
        max_value = max_calibrate[0]

        _LOGGER.debug(
            f"{self._source_entity.entity_id}: Linear mode state value: {value} range({min_value}-{max_value})"
        )
        if value is None:
            return None

        min_power = min_calibrate[1]
        max_power = max_calibrate[1]

        value_range = max_value - min_value
        if value_range == 0:
            return Decimal(min_power)

        power_range = max_power - min_power

        gamma_curve = self._config.get(CONF_GAMMA_CURVE) or 1

        relative_value = (value - min_value) / value_range

        power = power_range * relative_value**gamma_curve + min_power

        return Decimal(power)

    def get_min_calibrate(self, value: int) -> tuple[int, float]:
        """Get closest lower value from calibration table"""
        return min(self._calibration, key=lambda v: (v[0] > value, value - v[0]))

    def get_max_calibrate(self, value: int) -> tuple[int, float]:
        """Get closest higher value from calibration table"""
        return max(self._calibration, key=lambda v: (v[0] > value, value - v[0]))

    def create_calibrate_list(self) -> list[tuple]:
        """Build a table of calibration values"""
        list = []

        calibrate = self._config.get(CONF_CALIBRATE)
        if calibrate is None:
            full_range = self.get_entity_value_range()
            min = full_range[0]
            max = full_range[1]
            min_power = self._config.get(CONF_MIN_POWER) or self._standby_power or 0
            list.append((min, float(min_power)))
            list.append((max, float(self._config.get(CONF_MAX_POWER))))
            return list

        for line in calibrate:
            parts = line.split(" -> ")
            list.append((int(parts[0]), float(parts[1])))

        sorted_list = sorted(list, key=lambda tup: tup[0])
        return sorted_list

    def get_entity_value_range(self) -> tuple:
        """Get the min/max range for a given entity domain"""
        if self._source_entity.domain == fan.DOMAIN:
            return (0, 100)

        if self._source_entity.domain == light.DOMAIN:
            return (0, 255)

    def get_current_state_value(self, entity_state: State) -> Optional[int]:
        """Get the current entity state, i.e. selected brightness"""
        attrs = entity_state.attributes

        if entity_state.domain == light.DOMAIN:
            value = attrs.get(ATTR_BRIGHTNESS)
            # Some integrations set a higher brightness value than 255, causing powercalc to misbehave
            if value > 255:
                value = 255
            if value is None:
                _LOGGER.error(f"No brightness for entity: {entity_state.entity_id}")
                return None
            return value

        if entity_state.domain == fan.DOMAIN:
            value = attrs.get(ATTR_PERCENTAGE)
            if value is None:
                _LOGGER.error(f"No percentage for entity: {entity_state.entity_id}")
                return None
            return value

        try:
            return int(float(entity_state.state))
        except ValueError as e:
            _LOGGER.error(
                f"Expecting state to be a number for entity: {entity_state.entity_id}"
            )
            return None

    async def validate_config(self, source_entity: SourceEntity):
        """Validate correct setup of the strategy"""

        if (
            not CONF_CALIBRATE in self._config
            and source_entity.domain not in ALLOWED_DOMAINS
        ):
            raise StrategyConfigurationError(
                "Entity domain not supported for linear mode. Must be one of: {}".format(
                    ",".join(ALLOWED_DOMAINS)
                )
            )

        if not CONF_CALIBRATE in self._config and not CONF_MAX_POWER in self._config:
            raise StrategyConfigurationError(
                "Linear strategy must have at least 'max power' or 'calibrate' defined"
            )
