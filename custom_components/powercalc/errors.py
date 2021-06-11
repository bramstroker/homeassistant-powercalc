"""Errors for the power component."""
from homeassistant.exceptions import HomeAssistantError

class StrategyConfigurationError(HomeAssistantError):
    """Raised when strategy is not setup correctly."""

class LightNotSupported(StrategyConfigurationError):
    """Raised when light model is not supported."""

class UnsupportedMode(HomeAssistantError):
    """Mode not supported."""

class LutFileNotFound(HomeAssistantError):
    """Raise when LUT CSV file does not exist"""