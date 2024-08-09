from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MODE,
    CONF_MULTI_SWITCH,
    CONF_PLAYBOOK,
    CONF_WLED,
    CalculationStrategy,
)
from custom_components.powercalc.errors import UnsupportedStrategyError
from custom_components.powercalc.power_profile.power_profile import PowerProfile

STRATEGY_CONFIG_MAP = {
    CONF_LINEAR: CalculationStrategy.LINEAR,
    CONF_FIXED: CalculationStrategy.FIXED,
    CONF_MULTI_SWITCH: CalculationStrategy.MULTI_SWITCH,
    CONF_PLAYBOOK: CalculationStrategy.PLAYBOOK,
    CONF_WLED: CalculationStrategy.WLED,
    CONF_COMPOSITE: CalculationStrategy.COMPOSITE,
}


def detect_calculation_strategy(
    config: ConfigType,
    power_profile: PowerProfile | None,
) -> CalculationStrategy:
    """Select the calculation strategy."""
    config_mode = config.get(CONF_MODE)
    if config_mode:
        return CalculationStrategy(config_mode)

    for config_key, strategy in STRATEGY_CONFIG_MAP.items():
        if config.get(config_key):
            return strategy

    if power_profile:
        return power_profile.calculation_strategy

    raise UnsupportedStrategyError(
        "Cannot select a strategy, supply it in the config. See the readme",
    )
