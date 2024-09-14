import json
import os
from typing import Any, cast

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
        self._manufacturer_listing: dict[str, set[str]] = {}

    async def initialize(self) -> None:
        """Initialize the loader."""

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""
        cache_key = device_type or "all"
        if self._manufacturer_listing.get(cache_key):
            return self._manufacturer_listing[cache_key]

        def _find_manufacturer_directories() -> set[str]:
            return set(next(os.walk(self._data_directory))[1])

        manufacturer_dirs = await self._hass.async_add_executor_job(_find_manufacturer_directories)  # type: ignore[arg-type]

        manufacturers: set[str] = set()
        for manufacturer in manufacturer_dirs:
            models = await self.get_model_listing(manufacturer, device_type)
            if not models:
                continue
            manufacturers.add(manufacturer)

        self._manufacturer_listing[cache_key] = manufacturers
        return manufacturers

    async def find_manufacturer(self, search: str) -> str | None:
        """Check if a manufacturer is available. Also must check aliases."""
        manufacturer_list = await self.get_manufacturer_listing(None)
        if search in [m.lower() for m in manufacturer_list]:
            return search

        return None

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        models: set[str] = set()
        manufacturer_dir = os.path.join(self._data_directory, manufacturer)
        if not os.path.exists(manufacturer_dir):
            return models
        for model in await self._hass.async_add_executor_job(os.listdir, manufacturer_dir):
            if model[0] in [".", "@"] or model == "manufacturer.json":
                continue

            def _load_model_json(model_name: str) -> dict[str, Any]:
                """Load model.json file for a given model."""
                with open(os.path.join(manufacturer_dir, model_name, "model.json")) as f:
                    return cast(dict[str, Any], json.load(f))

            model_json = await self._hass.async_add_executor_job(_load_model_json, model)

            supported_device_type = DeviceType(model_json.get("device_type", DeviceType.LIGHT))
            if device_type and device_type != supported_device_type:
                continue
            models.add(model)
            self._model_aliases[manufacturer_dir] = model_json.get("aliases", [])
        return models

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        """Load a model.json file from disk for a given manufacturer and model."""
        base_dir = (
            self._data_directory
            if self._is_custom_directory
            else os.path.join(
                self._data_directory,
                manufacturer.lower(),
                model,
            )
        )

        if not os.path.exists(base_dir):
            return None

        model_json_path = os.path.join(base_dir, "model.json")
        if not model_json_path or not os.path.exists(model_json_path):
            raise LibraryLoadingError(f"model.json not found for {manufacturer} {model}")

        def _load_json() -> dict[str, Any]:
            """Load model.json file for a given model."""
            with open(model_json_path) as file:
                return cast(dict[str, Any], json.load(file))

        model_json = await self._hass.async_add_executor_job(_load_json)  # type: ignore
        return model_json, base_dir

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        """Find a model for a given manufacturer. Also must check aliases."""
        manufacturer_dir = os.path.join(self._data_directory, manufacturer)
        if not os.path.exists(manufacturer_dir):
            return None

        model_dirs = await self._hass.async_add_executor_job(os.listdir, manufacturer_dir)
        for model in search:
            if model in model_dirs:
                return model

        return None
