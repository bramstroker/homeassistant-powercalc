"""Errors for the power component."""
from homeassistant.exceptions import HomeAssistantError


class PowercalcSetupError(HomeAssistantError):
    """Raised when an error occured during powercalc sensor setup."""


class SensorConfigurationError(PowercalcSetupError):
    """Raised when sensor configuration is invalid"""


class StrategyConfigurationError(PowercalcSetupError):
    """Raised when strategy is not setup correctly."""


class ModelNotSupported(StrategyConfigurationError):
    """Raised when model is not supported."""


class UnsupportedMode(PowercalcSetupError):
    """Mode not supported."""


class LutFileNotFound(PowercalcSetupError):
    """Raised when LUT CSV file does not exist"""
