"""The PowerCalc integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.typing import HomeAssistantType

from .const import (
    CONF_ENTITY_NAME_PATTERN,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MAX_WATT,
    CONF_MIN_POWER,
    CONF_MIN_WATT,
    CONF_POWER,
    CONF_STATES_POWER,
    CONF_WATT,
    DATA_CALCULATOR_FACTORY,
    DOMAIN,
    DOMAIN_CONFIG,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT,
)
from .errors import StrategyConfigurationError, UnsupportedMode
from .light_model import LightModel
from .strategy_fixed import FixedStrategy
from .strategy_interface import PowerCalculationStrategyInterface
from .strategy_linear import LinearStrategy
from .strategy_lut import LutRegistry, LutStrategy

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
DEFAULT_NAME_PATTERN = "{} power"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): cv.time_period,
                vol.Optional(
                    CONF_ENTITY_NAME_PATTERN, default=DEFAULT_NAME_PATTERN
                ): vol.Match(r"\{\}"),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    conf = config.get(DOMAIN) or {
        CONF_ENTITY_NAME_PATTERN: DEFAULT_NAME_PATTERN,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }

    hass.data[DOMAIN] = {
        DATA_CALCULATOR_FACTORY: PowerCalculatorStrategyFactory(hass),
        DOMAIN_CONFIG: conf,
    }

    return True


class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(
        self,
        config: dict,
        mode: str,
        light_model: Optional[LightModel],
        entity_domain: str,
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration"""
        if mode == MODE_LINEAR:
            return self._create_linear(config, light_model, entity_domain)

        if mode == MODE_FIXED:
            return self._create_fixed(config, light_model)

        if mode == MODE_LUT:
            return self._create_lut(light_model)

        raise UnsupportedMode("Invalid calculation mode", mode)

    def _create_linear(
        self, config: dict, light_model: LightModel, entity_domain: str
    ) -> LinearStrategy:
        """Create the linear strategy"""
        linear_config = config.get(CONF_LINEAR)

        if linear_config is None:
            # Below is for BC compatibility
            if config.get(CONF_MIN_WATT) is not None:
                _LOGGER.warning(
                    "min_watt is deprecated and will be removed in version 0.3, use linear->min_power"
                )
                linear_config = {
                    CONF_MIN_POWER: config.get(CONF_MIN_WATT),
                    CONF_MAX_POWER: config.get(CONF_MAX_WATT),
                }

            elif light_model is not None:
                linear_config = light_model.linear_mode_config

        return LinearStrategy(linear_config, entity_domain)

    def _create_fixed(self, config: dict, light_model: LightModel) -> FixedStrategy:
        """Create the fixed strategy"""
        fixed_config = config.get(CONF_FIXED)
        if fixed_config is None and light_model is not None:
            fixed_config = light_model.fixed_mode_config

        # BC compat
        if fixed_config is None:
            _LOGGER.warning(
                "watt is deprecated and will be removed in version 0.3, use fixed->power"
            )
            fixed_config = {CONF_POWER: config.get(CONF_WATT)}

        return FixedStrategy(
            fixed_config.get(CONF_POWER), fixed_config.get(CONF_STATES_POWER)
        )

    def _create_lut(self, light_model: LightModel) -> LutStrategy:
        """Create the lut strategy"""
        if light_model is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode"
            )

        return LutStrategy(self._lut_registry, light_model)
