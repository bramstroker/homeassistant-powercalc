import json
import os

from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType


class LocalLoader(Loader):
    def __init__(self, hass: HomeAssistant, directory: str, is_custom_directory: bool = False) -> None:
        self._model_aliases: dict[str, dict[str, str]] = {}
        self._is_custom_directory = is_custom_directory
        self._data_directory = directory
        self._hass = hass

    async def initialize(self) -> None:
        pass

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""

        manufacturers: set[str] = set()
        for manufacturer in next(os.walk(self._data_directory))[1]:
            models = await self.get_model_listing(manufacturer, device_type)
            if not models:
                continue
            manufacturers.add(manufacturer)
        return manufacturers

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        models: set[str] = set()
        manufacturer_dir = os.path.join(self._data_directory, manufacturer)
        if not os.path.exists(manufacturer_dir):
            return models
        for model in os.listdir(manufacturer_dir):
            if model[0] in [".", "@"]:
                continue
            with open(os.path.join(manufacturer_dir, model, "model.json")) as f:
                model_json = json.load(f)
            supported_device_type = DeviceType(model_json.get("device_type", DeviceType.LIGHT))
            if device_type and device_type != supported_device_type:
                continue
            models.add(model)
            self._model_aliases[manufacturer_dir] = model_json.get("aliases", [])
        return models

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        base_dir = self._data_directory if self._is_custom_directory else os.path.join(
            self._data_directory,
            manufacturer.lower(),
            model,
        )

        if not os.path.exists(base_dir):
            return None

        model_json_path = os.path.join(base_dir, "model.json")
        if not model_json_path or not os.path.exists(model_json_path):
            raise LibraryLoadingError(f"model.json not found for {manufacturer} {model}")

        with open(model_json_path) as file:
            return json.load(file), base_dir

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        manufacturer_dir = os.path.join(self._data_directory, manufacturer)
        if not os.path.exists(manufacturer_dir):
            return None
        model_dirs = os.listdir(manufacturer_dir)
        for model in search:
            if model in model_dirs:
                return model

        return None
