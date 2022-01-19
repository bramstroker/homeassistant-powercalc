from typing import Optional

from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_LINEAR,
    CONF_POWER,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_WLED,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT,
    MODE_WLED,
)
from custom_components.powercalc.errors import (
    StrategyConfigurationError,
    UnsupportedMode,
)
from custom_components.powercalc.light_model import LightModel
from custom_components.powercalc.strategy.fixed import FixedStrategy
from custom_components.powercalc.strategy.linear import LinearStrategy
from custom_components.powercalc.strategy.lut import LutRegistry, LutStrategy
from custom_components.powercalc.strategy.strategy_interface import (
    PowerCalculationStrategyInterface,
)
from custom_components.powercalc.strategy.wled import WledStrategy


class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(
        self,
        config: dict,
        mode: str,
        light_model: Optional[LightModel],
        source_entity: SourceEntity,
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration"""
        if mode == MODE_LINEAR:
            return self._create_linear(config, light_model, source_entity)

        if mode == MODE_FIXED:
            return self._create_fixed(config, light_model)

        if mode == MODE_LUT:
            return self._create_lut(light_model)

        if mode == MODE_WLED:
            return self._create_wled(config, source_entity)

        raise UnsupportedMode("Invalid calculation mode", mode)

    def _create_linear(
        self, config: dict, light_model: LightModel, source_entity: SourceEntity
    ) -> LinearStrategy:
        """Create the linear strategy"""
        linear_config = config.get(CONF_LINEAR)

        if linear_config is None and light_model is not None:
            linear_config = light_model.linear_mode_config

        return LinearStrategy(
            linear_config, self._hass, source_entity, config.get(CONF_STANDBY_POWER)
        )

    def _create_fixed(self, config: dict, light_model: LightModel) -> FixedStrategy:
        """Create the fixed strategy"""
        fixed_config = config.get(CONF_FIXED)
        if fixed_config is None and light_model is not None:
            fixed_config = light_model.fixed_mode_config

        power = fixed_config.get(CONF_POWER)
        if isinstance(power, Template):
            power.hass = self._hass

        states_power = fixed_config.get(CONF_STATES_POWER)
        if states_power:
            for p in states_power.values():
                if isinstance(p, Template):
                    p.hass = self._hass

        return FixedStrategy(power, states_power)

    def _create_lut(self, light_model: LightModel) -> LutStrategy:
        """Create the lut strategy"""
        if light_model is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode"
            )

        return LutStrategy(self._lut_registry, light_model)

    def _create_wled(self, config: dict, source_entity: SourceEntity) -> WledStrategy:
        """Create the WLED strategy"""
        return WledStrategy(
            config=config.get(CONF_WLED),
            light_entity=source_entity,
            hass=self._hass,
            standby_power=config.get(CONF_STANDBY_POWER),
        )
