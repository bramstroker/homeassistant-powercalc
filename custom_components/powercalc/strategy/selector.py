from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_COMPOSITE,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MODE,
    CONF_PLAYBOOK,
    CONF_WLED,
    CalculationStrategy,
)
from custom_components.powercalc.errors import UnsupportedStrategyError
from custom_components.powercalc.power_profile.power_profile import PowerProfile


def detect_calculation_strategy(
    config: ConfigType,
    power_profile: PowerProfile | None,
) -> CalculationStrategy:
    """Select the calculation strategy."""
    config_mode = config.get(CONF_MODE)
    if config_mode:
        return CalculationStrategy(config_mode)

    if config.get(CONF_LINEAR):
        return CalculationStrategy.LINEAR

    if config.get(CONF_FIXED):
        return CalculationStrategy.FIXED

    if config.get(CONF_PLAYBOOK):
        return CalculationStrategy.PLAYBOOK

    if config.get(CONF_WLED):
        return CalculationStrategy.WLED

    if config.get(CONF_COMPOSITE):
        return CalculationStrategy.COMPOSITE

    if power_profile:
        return power_profile.calculation_strategy

    raise UnsupportedStrategyError(
        "Cannot select a strategy (LINEAR, FIXED or LUT, WLED), supply it in the config. See the readme",
    )
