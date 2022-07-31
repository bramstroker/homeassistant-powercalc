from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from ..common import SourceEntity
from ..const import (
    CONF_FIXED,
    CONF_LINEAR,
    CONF_POWER,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_WLED,
    CalculationStrategy,
)
from ..errors import StrategyConfigurationError, UnsupportedMode
from ..power_profile.light_model import LightModel
from .fixed import FixedStrategy
from .linear import LinearStrategy
from .lut import LutRegistry, LutStrategy
from .strategy_interface import PowerCalculationStrategyInterface
from .wled import WledStrategy


class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(
        self,
        config: dict,
        strategy: str,
        light_model: Optional[LightModel],
        source_entity: SourceEntity,
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration"""
        if strategy == CalculationStrategy.LINEAR:
            return self._create_linear(source_entity, config, light_model)

        if strategy == CalculationStrategy.FIXED:
            return self._create_fixed(source_entity, config, light_model)

        if strategy == CalculationStrategy.LUT:
            return self._create_lut(source_entity, light_model)

        if strategy == CalculationStrategy.WLED:
            return self._create_wled(source_entity, config)

        raise UnsupportedMode("Invalid calculation mode", strategy)

    def _create_linear(
        self, source_entity: SourceEntity, config: dict, light_model: LightModel
    ) -> LinearStrategy:
        """Create the linear strategy"""
        linear_config = config.get(CONF_LINEAR)

        if linear_config is None and light_model is not None:
            linear_config = light_model.linear_mode_config

        return LinearStrategy(
            linear_config, self._hass, source_entity, config.get(CONF_STANDBY_POWER)
        )

    def _create_fixed(
        self, source_entity: SourceEntity, config: dict, light_model: LightModel
    ) -> FixedStrategy:
        """Create the fixed strategy"""
        fixed_config = config.get(CONF_FIXED)
        if fixed_config is None and light_model is not None:
            fixed_config = light_model.fixed_mode_config

        power = fixed_config.get(CONF_POWER)
        if isinstance(power, Template):
            power.hass = self._hass

        states_power: dict = fixed_config.get(CONF_STATES_POWER)
        if states_power:
            for p in states_power.values():
                if isinstance(p, Template):
                    p.hass = self._hass

        return FixedStrategy(source_entity, power, states_power)

    def _create_lut(
        self, source_entity: SourceEntity, light_model: LightModel
    ) -> LutStrategy:
        """Create the lut strategy"""
        if light_model is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode"
            )

        return LutStrategy(source_entity, self._lut_registry, light_model)

    def _create_wled(self, source_entity: SourceEntity, config: dict) -> WledStrategy:
        """Create the WLED strategy"""
        return WledStrategy(
            config=config.get(CONF_WLED),
            light_entity=source_entity,
            hass=self._hass,
            standby_power=config.get(CONF_STANDBY_POWER),
        )
