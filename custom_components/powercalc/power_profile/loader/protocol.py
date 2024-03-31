from typing import Protocol

from custom_components.powercalc.power_profile.power_profile import DeviceType


class Loader(Protocol):
    def get_manufacturer_listing(self, device_type: DeviceType | None) -> list[str]:
        """Get listing of possible manufacturers."""
        ...

    def get_model_listing(self, manufacturer: str) -> list[str]:
        """Get listing of available models for a given manufacturer."""
        ...

    def load_model(self, manufacturer: str, model: str, directory: str | None) -> tuple[dict, str] | None:
        """Load and optionally download a model profile."""
        ...
