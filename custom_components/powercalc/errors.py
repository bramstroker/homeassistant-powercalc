"""Errors for the power component."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.exceptions import HomeAssistantError


class PowercalcSetupError(HomeAssistantError):
    """Raised when an error occured during powercalc sensor setup."""


class SensorConfigurationError(PowercalcSetupError):
    """Raised when sensor configuration is invalid"""


class SensorAlreadyConfiguredError(SensorConfigurationError):
    """Raised when power sensors has already been configured before for the entity"""

    def __init__(self, source_entity_id: str, existing_entities: list[SensorEntity]):
        self.existing_entities = existing_entities
        super().__init__(
            f"{source_entity_id}: This entity has already configured a power sensor"
        )

    def get_existing_entities(self):
        return self.existing_entities


class SensorAlreadyConfiguredError(SensorConfigurationError):
    """Raised when power sensors has already been configured before for the entity"""

    def __init__(self, source_entity_id: str, existing_entities: list[SensorEntity]):
        self.existing_entities = existing_entities
        super().__init__(
            f"{source_entity_id}: This entity has already configured a power sensor"
        )

    def get_existing_entities(self):
        return self.existing_entities


class StrategyConfigurationError(PowercalcSetupError):
    """Raised when strategy is not setup correctly."""


class ModelNotSupported(StrategyConfigurationError):
    """Raised when model is not supported."""


class UnsupportedMode(PowercalcSetupError):
    """Mode not supported."""


class LutFileNotFound(PowercalcSetupError):
    """Raised when LUT CSV file does not exist"""
