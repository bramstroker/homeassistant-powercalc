import logging

from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

_LOGGER = logging.getLogger(__name__)


class CompositeLoader(Loader):
    def __init__(self, loaders: list[Loader]) -> None:
        self.loaders = loaders

    async def initialize(self) -> None:
        [await loader.initialize() for loader in self.loaders]  # type: ignore[func-returns-value]

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""

        return {manufacturer for loader in self.loaders for manufacturer in await loader.get_manufacturer_listing(device_type)}

    async def find_manufacturer(self, search: str) -> str | None:
        """Check if a manufacturer is available. Also must check aliases."""

        search = search.lower()
        for loader in self.loaders:
            manufacturer = await loader.find_manufacturer(search)
            if manufacturer:
                return manufacturer

        return None

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        return {model for loader in self.loaders for model in await loader.get_model_listing(manufacturer, device_type)}

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        for loader in self.loaders:
            result = await loader.load_model(manufacturer, model)
            if result:
                return result

        return None

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        """Find the model in the library."""

        for loader in self.loaders:
            model = await loader.find_model(manufacturer, search)
            if model:
                return model

        return None
