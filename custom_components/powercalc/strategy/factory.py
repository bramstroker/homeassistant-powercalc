from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from homeassistant.const import CONF_CONDITION, CONF_ENTITIES
from homeassistant.core import HomeAssistant
from homeassistant.helpers import condition
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MULTI_SWITCH,
    CONF_PLAYBOOK,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_POWER_TEMPLATE,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_WLED,
    CalculationStrategy,
)
from custom_components.powercalc.errors import (
    StrategyConfigurationError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.power_profile.power_profile import PowerProfile

from .composite import CompositeStrategy, SubStrategy
from .fixed import FixedStrategy
from .linear import LinearStrategy
from .lut import LutRegistry, LutStrategy
from .multi_switch import MultiSwitchStrategy
from .playbook import PlaybookStrategy
from .selector import detect_calculation_strategy
from .strategy_interface import PowerCalculationStrategyInterface
from .wled import WledStrategy


class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry(hass)

    async def create(
        self,
        config: dict,
        strategy: str,
        power_profile: PowerProfile | None,
        source_entity: SourceEntity,
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration."""
        strategy_mapping: dict[str, Callable[[], PowerCalculationStrategyInterface]] = {
            CalculationStrategy.LINEAR: lambda: self._create_linear(source_entity, config, power_profile),
            CalculationStrategy.FIXED: lambda: self._create_fixed(source_entity, config, power_profile),
            CalculationStrategy.LUT: lambda: self._create_lut(source_entity, power_profile),
            CalculationStrategy.MULTI_SWITCH: lambda: self._create_multi_switch(config, power_profile),
            CalculationStrategy.PLAYBOOK: lambda: self._create_playbook(config),
            CalculationStrategy.WLED: lambda: self._create_wled(source_entity, config),
        }

        if strategy == CalculationStrategy.COMPOSITE:
            return await self._create_composite(config, power_profile, source_entity)

        if strategy in strategy_mapping:
            return strategy_mapping[strategy]()

        raise UnsupportedStrategyError("Invalid calculation mode", strategy)

    def _create_linear(
        self,
        source_entity: SourceEntity,
        config: dict,
        power_profile: PowerProfile | None,
    ) -> LinearStrategy:
        """Create the linear strategy."""
        linear_config = config.get(CONF_LINEAR)

        if linear_config is None:
            if power_profile and power_profile.linear_mode_config:
                linear_config = power_profile.linear_mode_config
            else:
                raise StrategyConfigurationError("No linear configuration supplied")

        return LinearStrategy(
            linear_config,
            self._hass,
            source_entity,
            config.get(CONF_STANDBY_POWER),
        )

    def _create_fixed(
        self,
        source_entity: SourceEntity,
        config: dict,
        power_profile: PowerProfile | None,
    ) -> FixedStrategy:
        """Create the fixed strategy."""
        fixed_config = config.get(CONF_FIXED)
        if fixed_config is None:
            if power_profile and power_profile.fixed_mode_config:
                fixed_config = power_profile.fixed_mode_config
            else:
                raise StrategyConfigurationError("No fixed configuration supplied")

        power = fixed_config.get(CONF_POWER)
        if power is None:
            power = fixed_config.get(CONF_POWER_TEMPLATE)
        if isinstance(power, Template):
            power.hass = self._hass

        states_power: dict = fixed_config.get(CONF_STATES_POWER)  # type: ignore
        if states_power:
            for p in states_power.values():
                if isinstance(p, Template):
                    p.hass = self._hass

        return FixedStrategy(source_entity, power, states_power)

    def _create_lut(
        self,
        source_entity: SourceEntity,
        power_profile: PowerProfile | None,
    ) -> LutStrategy:
        """Create the lut strategy."""
        if power_profile is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode",
            )

        return LutStrategy(source_entity, self._lut_registry, power_profile)

    def _create_wled(self, source_entity: SourceEntity, config: dict) -> WledStrategy:
        """Create the WLED strategy."""
        if CONF_WLED not in config:
            raise StrategyConfigurationError("No WLED configuration supplied")

        return WledStrategy(
            config=config.get(CONF_WLED),  # type: ignore
            light_entity=source_entity,
            hass=self._hass,
            standby_power=config.get(CONF_STANDBY_POWER),
        )

    def _create_playbook(self, config: ConfigType) -> PlaybookStrategy:
        if CONF_PLAYBOOK not in config:
            raise StrategyConfigurationError("No Playbook configuration supplied")

        playbook_config = config.get(CONF_PLAYBOOK)
        return PlaybookStrategy(self._hass, playbook_config)  # type: ignore

    async def _create_composite(
        self,
        config: ConfigType,
        power_profile: PowerProfile | None,
        source_entity: SourceEntity,
    ) -> CompositeStrategy:
        sub_strategies = list(config.get(CONF_COMPOSITE))  # type: ignore

        async def _create_sub_strategy(strategy_config: ConfigType) -> SubStrategy:
            condition_instance = None
            condition_config = strategy_config.get(CONF_CONDITION)
            if condition_config:
                condition_instance = await condition.async_from_config(
                    self._hass,
                    condition_config,
                )

            strategy = detect_calculation_strategy(strategy_config, power_profile)
            strategy_instance = await self.create(
                strategy_config,
                strategy,
                power_profile,
                source_entity,
            )
            return SubStrategy(condition_config, condition_instance, strategy_instance)

        strategies = [await _create_sub_strategy(config) for config in sub_strategies]
        return CompositeStrategy(self._hass, strategies)

    def _create_multi_switch(self, config: ConfigType, power_profile: PowerProfile | None) -> MultiSwitchStrategy:
        """Create instance of multi switch strategy."""
        multi_switch_config: ConfigType = {}
        if power_profile and power_profile.multi_switch_mode_config:
            multi_switch_config = power_profile.multi_switch_mode_config
        multi_switch_config.update(config.get(CONF_MULTI_SWITCH, {}))

        if not multi_switch_config:
            raise StrategyConfigurationError("No multi_switch configuration supplied")

        entities: list[str] = multi_switch_config.get(CONF_ENTITIES, [])
        if not entities:
            raise StrategyConfigurationError("No switch entities supplied")

        on_power: Decimal | None = multi_switch_config.get(CONF_POWER)
        off_power: Decimal | None = multi_switch_config.get(CONF_POWER_OFF)
        if off_power is None or on_power is None:
            raise StrategyConfigurationError("No power configuration supplied")

        return MultiSwitchStrategy(
            self._hass,
            entities,
            on_power=Decimal(on_power),
            off_power=Decimal(off_power),
        )
