from __future__ import annotations

from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from ..common import SourceEntity
from ..const import (
    CONF_FIXED,
    CONF_LINEAR,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_WLED,
    CalculationStrategy,
)
from ..errors import StrategyConfigurationError, UnsupportedStrategy
from ..power_profile.power_profile import PowerProfile
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
        power_profile: Optional[PowerProfile],
        source_entity: SourceEntity,
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration"""
        if strategy == CalculationStrategy.LINEAR:
            return self._create_linear(source_entity, config, power_profile)

        if strategy == CalculationStrategy.FIXED:
            return self._create_fixed(source_entity, config, power_profile)

        if strategy == CalculationStrategy.LUT:
            return self._create_lut(source_entity, power_profile)

        if strategy == CalculationStrategy.WLED:
            return self._create_wled(source_entity, config)

        raise UnsupportedStrategy("Invalid calculation mode", strategy)

    def _create_linear(
        self, source_entity: SourceEntity, config: dict, power_profile: PowerProfile
    ) -> LinearStrategy:
        """Create the linear strategy"""
        linear_config = config.get(CONF_LINEAR)

        if linear_config is None and power_profile is not None:
            linear_config = power_profile.linear_mode_config

        return LinearStrategy(
            linear_config, self._hass, source_entity, config.get(CONF_STANDBY_POWER)
        )

    def _create_fixed(
        self, source_entity: SourceEntity, config: dict, power_profile: PowerProfile
    ) -> FixedStrategy:
        """Create the fixed strategy"""
        fixed_config = config.get(CONF_FIXED)
        if fixed_config is None and power_profile is not None:
            fixed_config = power_profile.fixed_mode_config

        power = fixed_config.get(CONF_POWER)
        if power is None:
            power = fixed_config.get(CONF_POWER_TEMPLATE)
        if isinstance(power, Template):
            power.hass = self._hass

        states_power: dict = fixed_config.get(CONF_STATES_POWER)
        if states_power:
            for p in states_power.values():
                if isinstance(p, Template):
                    p.hass = self._hass

        return FixedStrategy(source_entity, power, states_power)

    def _create_lut(
        self, source_entity: SourceEntity, power_profile: PowerProfile
    ) -> LutStrategy:
        """Create the lut strategy"""
        if power_profile is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode"
            )

        return LutStrategy(source_entity, self._lut_registry, power_profile)

    def _create_wled(self, source_entity: SourceEntity, config: dict) -> WledStrategy:
        """Create the WLED strategy"""
        return WledStrategy(
            config=config.get(CONF_WLED),
            light_entity=source_entity,
            hass=self._hass,
            standby_power=config.get(CONF_STANDBY_POWER),
        )
