import json
import logging
import os
import re
from typing import Any, cast

from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType, PowerProfile

_LOGGER = logging.getLogger(__name__)


class LocalLoader(Loader):
    def __init__(self, hass: HomeAssistant, directory: str, is_custom_directory: bool = False) -> None:
        self._is_custom_directory = is_custom_directory
        self._data_directory = directory
        self._hass = hass
        self._manufacturer_model_listing: dict[str, dict[str, PowerProfile]] = {}

    async def initialize(self) -> None:
        """Initialize the loader."""
        if not self._is_custom_directory:
            await self._hass.async_add_executor_job(self._load_custom_library)

    async def get_manufacturer_listing(self, device_types: set[DeviceType] | None) -> set[tuple[str, str]]:
        """Get listing of all available manufacturers or filtered by model device_type."""
        if device_types is None:
            return {(manufacturer, manufacturer) for manufacturer in self._manufacturer_model_listing}

        manufacturers: set[tuple[str, str]] = set()
        for manufacturer in self._manufacturer_model_listing:
            models = await self.get_model_listing(manufacturer, device_types)
            if not models:
                continue
            manufacturers.add((manufacturer, manufacturer))

        return manufacturers

    async def find_manufacturers(self, search: str) -> set[str]:
        """Check if a manufacturer is available."""

        _search = search.lower()
        manufacturer_list = self._manufacturer_model_listing.keys()
        if _search in manufacturer_list:
            return {_search}

        return set()

    async def get_model_listing(self, manufacturer: str, device_types: set[DeviceType] | None) -> set[str]:
        """Get listing of available models for a given manufacturer.

        param manufacturer: manufacturer always handled in lower case
        param device_type:  models of the manufacturer will be filtered by DeviceType, models
                            without assigned device_type will be handled as DeviceType.LIGHT.
                            None will return all models of a manufacturer.
        returns:            Set[str] of models
        """

        found_models: set[str] = set()
        models = self._manufacturer_model_listing.get(manufacturer.lower())
        if not models:
            return found_models

        for profile in models.values():
            if device_types and profile.device_type not in device_types:
                continue
            found_models.add(profile.model)

        return found_models

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        """Load a model.json file from disk for a given manufacturer.lower() and model.lower()
        by querying the custom library.
        If self._is_custom_directory == true model.json will be loaded directly from there.

        returns: tuple[dict, str] model.json as dictionary and model as lower case
        returns: None when manufacturer, model or model path not found
        raises LibraryLoadingError: model.json not found
        """
        _manufacturer = manufacturer.lower()
        _model = model.lower()

        if self._is_custom_directory:
            model_path = os.path.join(self._data_directory)
            model_json_path = os.path.join(model_path, "model.json")
            if not os.path.exists(model_json_path):
                raise LibraryLoadingError(f"model.json not found for manufacturer {_manufacturer} " + f"and model {_model} in path {model_json_path}")

            model_json = await self._hass.async_add_executor_job(self._load_json, model_json_path)
            return model_json, model_path

        lib_models = self._manufacturer_model_listing.get(_manufacturer)
        if lib_models is None:
            return None

        lib_model = lib_models.get(_model)
        if lib_model is None:
            return None

        model_path = lib_model.get_model_directory()
        model_json = lib_model.json_data
        return model_json, model_path

    async def find_model(self, manufacturer: str, search: set[str]) -> list[str]:
        """Find a model for a given manufacturer. Also must check aliases."""
        _manufacturer = manufacturer.lower()

        models = self._manufacturer_model_listing.get(_manufacturer)
        if not models:
            return []

        search_lower = {phrase.lower() for phrase in search}

        profile = next((models[model] for model in models if model.lower() in search_lower), None)
        return [profile.model] if profile else []

    def _load_custom_library(self) -> None:
        """Loading custom models and aliases from file system.
        Manufacturer directories without model directories and model.json files within
        are not loaded. Same is with model directories without model.json files.
        """

        base_path = self._data_directory

        if not os.path.exists(base_path):
            _LOGGER.error("Custom library directory does not exist: %s", base_path)
            return

        self._manufacturer_model_listing.clear()
        for manufacturer_dir in next(os.walk(base_path))[1]:
            manufacturer_path = os.path.join(base_path, manufacturer_dir)

            manufacturer = manufacturer_dir.lower()
            for model_dir in next(os.walk(manufacturer_path))[1]:
                pattern = re.compile(r"^\..*")
                if pattern.match(model_dir):
                    continue

                model_path = os.path.join(manufacturer_path, model_dir)

                model_json_path = os.path.join(model_path, "model.json")
                if not os.path.exists(model_json_path):
                    _LOGGER.warning("model.json should exist in %s!", model_path)
                    continue

                model_json = self._load_json(model_json_path)
                profile = PowerProfile(
                    self._hass,
                    manufacturer=manufacturer,
                    model=model_dir,
                    directory=model_path,
                    json_data=model_json,
                )

                self._add_profile_to_library(profile)
                for alias in profile.aliases:
                    self._add_profile_to_library(
                        PowerProfile(
                            self._hass,
                            manufacturer=manufacturer,
                            model=alias,
                            directory=model_path,
                            json_data=model_json,
                        ),
                    )

    def _add_profile_to_library(self, profile: PowerProfile) -> None:
        """Add profile to the library lookup dictionary."""
        manufacturer = profile.manufacturer
        if self._manufacturer_model_listing.get(manufacturer) is None:
            self._manufacturer_model_listing[manufacturer] = {}

        search_key = profile.model.lower()
        if self._manufacturer_model_listing[manufacturer].get(search_key):
            _LOGGER.error(
                "Double entry manufacturer/model in custom library: %s/%s",
                profile.manufacturer,
                profile.model,
            )
            return

        self._manufacturer_model_listing[manufacturer].update({search_key: profile})

    def _load_json(self, model_json_path: str) -> dict[str, Any]:
        """Load model.json file for a given model."""
        with open(model_json_path) as file:
            return cast(dict[str, Any], json.load(file))
