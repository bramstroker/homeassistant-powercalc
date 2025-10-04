from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

from homeassistant.const import CONF_CONDITION, CONF_ENTITIES, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import condition
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_MODE,
    CONF_MULTI_SWITCH,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_POWER_TEMPLATE,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_STRATEGIES,
    CalculationStrategy,
)
from custom_components.powercalc.errors import (
    StrategyConfigurationError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.power_profile.power_profile import PowerProfile

from .composite import DEFAULT_MODE, CompositeStrategy, SubStrategy
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

    @staticmethod
    @singleton("powercalc_strategy_factory")
    def get_instance(hass: HomeAssistant) -> PowerCalculatorStrategyFactory:
        return PowerCalculatorStrategyFactory(hass)

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
            CalculationStrategy.PLAYBOOK: lambda: self._create_playbook(config, power_profile),
            CalculationStrategy.WLED: lambda: self._create_wled(source_entity, config),
        }

        if strategy == CalculationStrategy.COMPOSITE:
            return await self._prepare(
                await self._create_composite(config, source_entity, power_profile),
            )

        if strategy in strategy_mapping:
            return await self._prepare(
                strategy_mapping[strategy](),
            )

        raise UnsupportedStrategyError("Invalid calculation strategy", strategy)

    @staticmethod
    async def _prepare(instance: PowerCalculationStrategyInterface) -> PowerCalculationStrategyInterface:
        await instance.validate_config()
        await instance.initialize()
        return instance

    def _create_linear(
        self,
        source_entity: SourceEntity,
        config: dict,
        power_profile: PowerProfile | None,
    ) -> LinearStrategy:
        """Create the linear strategy."""
        linear_config = self._get_strategy_config(CalculationStrategy.LINEAR, config, power_profile)

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
        fixed_config = self._get_strategy_config(CalculationStrategy.FIXED, config, power_profile)

        power = fixed_config.get(CONF_POWER)
        if power is None:
            power = fixed_config.get(CONF_POWER_TEMPLATE)
        power = self._resolve_template(power)

        states_power = fixed_config.get(CONF_STATES_POWER)
        if states_power:
            states_power = {state: self._resolve_template(value) for state, value in states_power.items()}

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
        wled_config = self._get_strategy_config(CalculationStrategy.WLED, config, None)
        return WledStrategy(
            config=wled_config,
            light_entity=source_entity,
            hass=self._hass,
            standby_power=config.get(CONF_STANDBY_POWER),
        )

    def _create_playbook(self, config: ConfigType, power_profile: PowerProfile | None) -> PlaybookStrategy:
        playbook_config = self._get_strategy_config(CalculationStrategy.PLAYBOOK, config, power_profile)

        directory = None
        if power_profile and power_profile.calculation_strategy == CalculationStrategy.PLAYBOOK:
            directory = power_profile.get_model_directory()

        return PlaybookStrategy(self._hass, playbook_config, directory)

    async def _create_composite(
        self,
        config: ConfigType,
        source_entity: SourceEntity,
        power_profile: PowerProfile | None,
    ) -> CompositeStrategy:
        composite_config: list | dict | None = config.get(CONF_COMPOSITE)
        if composite_config is None:
            if power_profile and power_profile.composite_config:
                composite_config = power_profile.composite_config
            else:
                raise StrategyConfigurationError("No composite configuration supplied")

        sub_strategies = composite_config
        mode = DEFAULT_MODE
        if isinstance(composite_config, dict):
            mode = composite_config.get(CONF_MODE, DEFAULT_MODE)
            sub_strategies = composite_config.get(CONF_STRATEGIES)  # type: ignore

        async def _create_sub_strategy(strategy_config: ConfigType) -> SubStrategy:
            condition_instance = None
            condition_config = strategy_config.get(CONF_CONDITION)
            if condition_config:
                condition_type = condition_config.get(CONF_CONDITION)
                if condition_type in ["state", "numeric_state"] and CONF_ENTITY_ID not in condition_config:
                    condition_config[CONF_ENTITY_ID] = [source_entity.entity_id]
                if condition_type == "state":
                    condition_config = condition.state_validate_config(self._hass, condition_config)
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
        return CompositeStrategy(self._hass, strategies, mode)

    def _create_multi_switch(self, config: ConfigType, power_profile: PowerProfile | None) -> MultiSwitchStrategy:
        """Create instance of multi switch strategy."""
        multi_switch_config: ConfigType = {}
        if power_profile and power_profile.multi_switch_config:
            multi_switch_config = power_profile.multi_switch_config
        multi_switch_config.update(config.get(CONF_MULTI_SWITCH, {}))

        if not multi_switch_config:
            raise StrategyConfigurationError("No multi_switch configuration supplied")

        entities: list[str] = multi_switch_config.get(CONF_ENTITIES, [])

        on_power: Decimal | None = multi_switch_config.get(CONF_POWER)
        off_power: Decimal | None = multi_switch_config.get(CONF_POWER_OFF)
        if on_power is None:
            raise StrategyConfigurationError("No power configuration supplied")

        return MultiSwitchStrategy(
            self._hass,
            entities,
            on_power=Decimal(on_power),
            off_power=Decimal(off_power) if off_power else None,
        )

    def _resolve_template(self, value: Any) -> Any:  # noqa: ANN401
        """
        Process the input to ensure it is a Template if applicable.
        Otherwise, return the original value.
        """
        if isinstance(value, str) and value.startswith("{{"):
            return Template(value, self._hass)
        if isinstance(value, Template):
            value.hass = self._hass
            return value
        return value

    @staticmethod
    def _get_strategy_config(
        strategy: CalculationStrategy,
        config: ConfigType,
        power_profile: PowerProfile | None,
    ) -> ConfigType:
        """Get the strategy configuration."""
        if strategy in config:
            return cast(ConfigType, config[strategy])

        prop = f"{strategy}_config"
        if power_profile and getattr(power_profile, prop):
            return cast(ConfigType, getattr(power_profile, prop))

        raise StrategyConfigurationError(f"No {strategy} configuration supplied")
