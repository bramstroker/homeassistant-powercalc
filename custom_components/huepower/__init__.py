"""The HuePower integration."""

from __future__ import annotations

from .const import (
    CONF_MODE,
    CONF_MIN_USAGE,
    CONF_MAX_USAGE,
    CONF_USAGE,
    DOMAIN,
    DATA_CALCULATOR_FACTORY,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT
)

from homeassistant.helpers.typing import HomeAssistantType

from .strategy_lut import (
    LutRegistry,
    LutStrategy
)
from .strategy_linear import (
    LinearStrategy
)
from .strategy_fixed import (
    FixedStrategy
)
from.strategy_interface import (
    PowerCalculationStrategyInterface
)

from .errors import UnsupportedMode

async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_CALCULATOR_FACTORY] = PowerCalculatorStrategyFactory(hass)

    return True

class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(self, config: str, manufacturer: str, model: str) -> PowerCalculationStrategyInterface:
        mode = config.get(CONF_MODE) or MODE_LUT

        if (mode == MODE_LINEAR):
            return LinearStrategy(
                min=config.get(CONF_MIN_USAGE),
                max=config.get(CONF_MAX_USAGE)
            )
        
        if (mode == MODE_FIXED):
            return FixedStrategy(
                wattage=config.get(CONF_USAGE)
            )
        
        if (mode == MODE_LUT):
            return LutStrategy(
                self._lut_registry,
                manufacturer=manufacturer,
                model=model
            )
        
        raise UnsupportedMode("Invalid calculation mode", mode)