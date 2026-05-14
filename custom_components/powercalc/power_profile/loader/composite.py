import logging

from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType, DiscoveryBy

_LOGGER = logging.getLogger(__name__)


class CompositeLoader(Loader):
    def __init__(self, loaders: list[Loader]) -> None:
        self.loaders = loaders

    async def initialize(self) -> None:
        for loader in self.loaders:
            await loader.initialize()

    async def get_manufacturer_listing(
        self,
        device_types: set[DeviceType] | None,
        discovery_by: DiscoveryBy | None = None,
    ) -> set[tuple[str, str]]:
        """Get listing of available manufacturers."""

        return {manufacturer for loader in self.loaders for manufacturer in await loader.get_manufacturer_listing(device_types, discovery_by)}

    async def find_manufacturers(self, search: str) -> set[str]:
        """Check if a manufacturer is available. Also must check aliases."""

        search = search.lower()
        found_manufacturers = set()
        for loader in self.loaders:
            manufacturers = await loader.find_manufacturers(search)
            if manufacturers:
                found_manufacturers.update(manufacturers)

        return found_manufacturers

    async def get_model_listing(
        self,
        manufacturer: str,
        device_types: set[DeviceType] | None,
        discovery_by: DiscoveryBy | None = None,
    ) -> set[tuple[str, str]]:
        """Get listing of available models and display names for a given manufacturer."""

        return {model for loader in self.loaders for model in await loader.get_model_listing(manufacturer, device_types, discovery_by)}

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        for loader in self.loaders:
            result = await loader.load_model(manufacturer, model)
            if result:
                return result

        return None

    async def find_model(self, manufacturer: str, search: set[str]) -> list[str]:
        """Find the model in the library."""

        models = []
        for loader in self.loaders:
            models.extend(await loader.find_model(manufacturer, search))

        return models

    async def find_model_migration(self, manufacturer: str, model: str) -> str | None:
        """Find the canonical model id for a legacy profile id."""
        matches: set[str] = set()
        for loader in self.loaders:
            migrated_model = await loader.find_model_migration(manufacturer, model)
            if migrated_model:
                matches.add(migrated_model)

        if len(matches) != 1:
            return None

        return next(iter(matches))
