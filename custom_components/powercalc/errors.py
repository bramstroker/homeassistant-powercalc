"""Errors for the power component."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class PowercalcSetupError(HomeAssistantError):
    """Raised when an error occured during powercalc sensor setup."""


class SensorConfigurationError(PowercalcSetupError):
    """Raised when sensor configuration is invalid."""


class SensorAlreadyConfiguredError(SensorConfigurationError):
    """Raised when power sensors has already been configured before for the entity."""

    def __init__(
        self,
        source_entity_id: str,
        existing_entities: list,
    ) -> None:
        self.existing_entities = existing_entities
        super().__init__(
            f"{source_entity_id}: This entity has already configured a power sensor. "
            "When you want to configure it twice make sure to give it a unique_id",
        )

    def get_existing_entities(self) -> list:
        return self.existing_entities


class StrategyConfigurationError(PowercalcSetupError):
    """Raised when strategy is not setup correctly."""

    def __init__(self, message: str, config_flow_trans_key: str | None = None) -> None:
        super().__init__(message)
        self._config_flow_trans_key = config_flow_trans_key

    def get_config_flow_translate_key(self) -> str | None:
        return self._config_flow_trans_key


class ModelNotSupportedError(StrategyConfigurationError):
    """Raised when model is not supported."""


class UnsupportedStrategyError(PowercalcSetupError):
    """Mode not supported."""


class LutFileNotFoundError(PowercalcSetupError):
    """Raised when LUT CSV file does not exist."""
