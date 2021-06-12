"""Errors for the power component."""
from homeassistant.exceptions import HomeAssistantError

class StrategyConfigurationError(HomeAssistantError):
    """Raised when strategy is not setup correctly."""

class ModelNotSupported(StrategyConfigurationError):
    """Raised when model is not supported."""

class UnsupportedMode(HomeAssistantError):
    """Mode not supported."""

class LutFileNotFound(HomeAssistantError):
    """Raised when LUT CSV file does not exist"""