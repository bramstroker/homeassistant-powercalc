"""The PowerCalc integration."""

from __future__ import annotations

from homeassistant.helpers.typing import HomeAssistantType

from .const import (
    CONF_MAX_WATT,
    CONF_MIN_WATT,
    CONF_MODE,
    CONF_WATT,
    DATA_CALCULATOR_FACTORY,
    DOMAIN,
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


async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_CALCULATOR_FACTORY] = PowerCalculatorStrategyFactory(hass)

    return True


class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(
        self, config: dict, mode: str, light_model: LightModel
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration"""
        if mode == MODE_LINEAR:
            return self.create_linear(config, light_model)

        if mode == MODE_FIXED:
            return self.create_fixed(config, light_model)

        if mode == MODE_LUT:
            return self.create_lut(light_model)

        raise UnsupportedMode("Invalid calculation mode", mode)

    def create_linear(self, config: dict, light_model: LightModel) -> LinearStrategy:
        """Create the linear strategy"""
        min = config.get(CONF_MIN_WATT)
        max = config.get(CONF_MAX_WATT)
        if min is None and max is None:
            min = light_model.linear_mode_config.get(CONF_MIN_WATT)
            max = light_model.linear_mode_config.get(CONF_MAX_WATT)

        return LinearStrategy(min, max)

    def create_fixed(self, config: dict, light_model: LightModel) -> FixedStrategy:
        """Create the fixed strategy"""
        return FixedStrategy(
            config.get(CONF_WATT) or light_model.fixed_mode_config.get(CONF_WATT)
        )

    def create_lut(self, light_model: LightModel) -> LutStrategy:
        """Create the lut strategy"""
        if light_model is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode"
            )

        return LutStrategy(self._lut_registry, light_model)
