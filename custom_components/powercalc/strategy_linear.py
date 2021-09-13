from __future__ import annotations

import logging
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import fan, light
from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.core import State
from homeassistant.helpers.config_validation import entity_domain

from .common import SourceEntity
from .const import CONF_CALIBRATE, CONF_MAX_POWER, CONF_MIN_POWER
from .errors import StrategyConfigurationError
from .strategy_interface import PowerCalculationStrategyInterface

ALLOWED_DOMAINS = [fan.DOMAIN, light.DOMAIN]
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CALIBRATE): vol.All(
            cv.ensure_list, [vol.Match("^[0-9]+ -> ([0-9]*[.])?[0-9]+$")]
        ),
        vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
        vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
    }
)

_LOGGER = logging.getLogger(__name__)


class LinearStrategy(PowerCalculationStrategyInterface):
    def __init__(self, config, entity_domain: str) -> None:
        self._config = config
        self._entity_domain = entity_domain
        self._calibration = self.create_calibrate_list()

    async def calculate(self, entity_state: State) -> Optional[float]:
        attrs = entity_state.attributes

        if entity_state.domain == light.DOMAIN:
            value = attrs.get(ATTR_BRIGHTNESS)
            # Some integrations set a higher brightness value than 255, causing powercalc to misbehave
            if value > 255:
                value = 255
            if value is None:
                _LOGGER.error("No brightness for entity: %s", entity_state.entity_id)
                return None

        if entity_state.domain == fan.DOMAIN:
            value = attrs.get(ATTR_PERCENTAGE)
            if value is None:
                _LOGGER.error("No percentage for entity: %s", entity_state.entity_id)
                return None

        min_calibrate = self.get_min_calibrate(value)
        max_calibrate = self.get_max_calibrate(value)
        min_value = min_calibrate[0]
        max_value = max_calibrate[0]
        min_power = min_calibrate[1]
        max_power = max_calibrate[1]

        value_range = max_value - min_value
        if value_range == 0:
            power = min_power
        else:
            power_range = max_power - min_power
            power = (((value - min_value) * power_range) / value_range) + min_power

        return round(power, 2)

    def get_min_calibrate(self, value: int) -> tuple[int, float]:
        return min(self._calibration, key=lambda v: (v[0] > value, value - v[0]))

    def get_max_calibrate(self, value: int) -> tuple[int, float]:
        return max(self._calibration, key=lambda v: (v[0] > value, value - v[0]))

    def create_calibrate_list(self) -> list[tuple]:
        list = []

        calibrate = self._config.get(CONF_CALIBRATE)
        if calibrate is None:
            list.append((1, float(self._config.get(CONF_MIN_POWER))))
            if entity_domain == fan.DOMAIN:
                max = 100
            else:
                max = 255
            list.append((max, float(self._config.get(CONF_MAX_POWER))))
            return list

        for line in calibrate:
            parts = line.split(" -> ")
            list.append((int(parts[0]), float(parts[1])))

        sorted_list = sorted(list, key=lambda tup: tup[0])
        return sorted_list

    async def validate_config(self, source_entity: SourceEntity):
        """Validate correct setup of the strategy"""

        if source_entity.domain not in ALLOWED_DOMAINS:
            raise StrategyConfigurationError(
                "Entity not supported for linear mode. Must be one of: {}".format(
                    ",".join(ALLOWED_DOMAINS)
                )
            )

        if self._config.get(CONF_CALIBRATE) is None:
            if self._config.get(CONF_MIN_POWER) is None:
                raise StrategyConfigurationError("You must supply min power")

            if self._config.get(CONF_MAX_POWER) is None:
                raise StrategyConfigurationError("You must supply max power")
