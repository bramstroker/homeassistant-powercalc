from typing import Protocol

from custom_components.powercalc.power_profile.power_profile import DeviceType


class Loader(Protocol):
    async def initialize(self) -> None:
        """Initialize the loader."""

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of possible manufacturers."""

    async def find_manufacturer(self, search: str) -> str | None:
        """Check if a manufacturer is available. Also must check aliases."""

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        """Load and optionally download a model profile."""

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        """Check if a model is available. Also must check aliases."""
