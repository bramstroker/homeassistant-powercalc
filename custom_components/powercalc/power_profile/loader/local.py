import json
import logging
import os
import re
from typing import Any, cast

from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

_LOGGER = logging.getLogger(__name__)


class LocalLoader(Loader):
    def __init__(self, hass: HomeAssistant, directory: str, is_custom_directory: bool = False) -> None:
        self._is_custom_directory = is_custom_directory
        self._data_directory = directory
        self._hass = hass

        self._manufacturer_model_listing: dict[str, dict[str, dict[str, str]]] = {}

    async def initialize(self) -> None:
        """Initialize the loader."""
        self._manufacturer_model_listing = await self._load_custom_library()

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of all available manufacturers or filtered by model device_type."""
        if device_type is None:
            return list(self._manufacturer_model_listing.keys())

        manufacturers: set[str] = set()
        for manufacturer in self._manufacturer_model_listing.keys():
            models = await self.get_model_listing(manufacturer, device_type)
            if not models:
                continue
            manufacturers.add(manufacturer)

        return manufacturers

    async def find_manufacturer(self, search: str) -> str | None:
        """Check if a manufacturer is available."""
        # QUESTION: Should this function return search or search.lower()?
        #             and should it do search.lower() in ... ?
        _search = search.lower()
        manufacturer_list = self._manufacturer_model_listing.keys()
        if _search in manufacturer_list:
            return _search

        return None

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer.

        param manufacturer: manufacturer always handled in lower case
        param device_type:  models of the manufacturer will be filtered by DeviceType, models
                            without assigned device_type will be handled as DeviceType.LIGHT.
                            None will return all models of a manufacturer.
        returns:            Set[str] of models
        """
        _manufacturer = manufacturer.lower()

        models: set[str] = set()
        if self._manufacturer_model_listing.get(_manufacturer) is None:
            return models

        for model in self._manufacturer_model_listing.get(_manufacturer):
            supported_device_type = DeviceType(self._manufacturer_model_listing.get(_manufacturer).get(model).get("device_type", DeviceType.LIGHT))
            if device_type and device_type != supported_device_type:
                continue
            models.add(model)

        return models

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None | LibraryLoadingError:
        """Load a model.json file from disk for a given manufacturer.lower() and model.lower()
        by querying the custom library.
        If self._is_custom_directory == true model.json will be loaded directy from there.

        returns: tuple[dict, str] model.json as dictionary and model as lower case
        returns: None when manufacturer, model or model path not found
        raises LibraryLoadingError: model.json not found
        """
        _manufacturer = manufacturer.lower()
        _model = model.lower()

        if not self._is_custom_directory:
            if self._manufacturer_model_listing == {}:
                self.initialize()

            lib_models = self._manufacturer_model_listing.get(_manufacturer)
            if lib_models is None:
                _LOGGER.info("Manufacturer does not exist in custom library: %s", _manufacturer)
                return None

            lib_model = lib_models.get(_model)
            if lib_model is None:
                _LOGGER.info("Model does not exist in custom library for manufacturer %s: %s", _manufacturer, _model)
                return None

            model_path = lib_model.get("path")
            if model_path is None:
                _LOGGER.warning("Model exists in custom library for manufacturer %s but does not " + "have a path: %s", _manufacturer, _model)
                return None
        else:
            model_path = os.path.join(self._data_directory)

        model_json_path = os.path.join(model_path, "model.json")
        if not os.path.exists(model_json_path):
            raise LibraryLoadingError(f"model.json not found for manufacturer {_manufacturer} " + f"and model {_model} in path {model_json_path}")

        def _load_json() -> dict[str, Any]:
            """Load model.json file for a given model."""
            with open(model_json_path) as file:
                return cast(dict[str, Any], json.load(file))

        model_json = await self._hass.async_add_executor_job(_load_json)  # type: ignore
        return model_json, model_path

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        """Find a model for a given manufacturer. Also must check aliases."""
        _manufacturer = manufacturer.lower()

        models = self._manufacturer_model_listing.get(_manufacturer)
        if not models:
            _LOGGER.info("Manufacturer does not exist in custom library: %s", _manufacturer)
            return None

        search_lower = {phrase.lower() for phrase in search}

        return next((model for model in models.keys() if model.lower() in search_lower), None)

    async def _load_custom_library(self) -> dict:
        """Loading custom models and aliases from file system.
        Manufacturer directories without model directrories and model.json files within
        are not loaded. Same is with model directories without model.json files.
        """

        # QUESTION: What is the difference originally when _is_custom_directory is true
        library: dict[str, dict[str, str]] = {}
        base_path = (
            self._data_directory
            if self._is_custom_directory
            else os.path.join(
                self._data_directory,
            )
        )

        if not os.path.exists(base_path):
            _LOGGER.warning("Custom library directory does not exist: %s", base_path)
            return library

        base_dir_content = await self._hass.async_add_executor_job(os.walk, base_path)
        base_dir_content = await self._hass.async_add_executor_job(next, base_dir_content)

        def _load_json() -> dict[str, Any]:
            """Load model.json file for a given model."""
            with open(model_json_path) as file:
                return cast(dict[str, Any], json.load(file))

        for manufacturer_dir in base_dir_content[1]:
            manufacturer_path = os.path.join(base_path, manufacturer_dir)
            if not os.path.exists(manufacturer_path):
                _LOGGER.error("Manufacturer directory %s should be there but is not!", manufacturer_path)
                continue

            model_dir_content = await self._hass.async_add_executor_job(os.walk, manufacturer_path)
            model_dir_content = await self._hass.async_add_executor_job(next, model_dir_content)

            manufacturer = manufacturer_dir.lower()
            for model_dir in model_dir_content[1]:
                pattern = re.compile(r"^\..*")
                if pattern.match(model_dir):
                    _LOGGER.info("Hidden model %s for manufacturer %s detected. Not imported!", model_dir, manufacturer)
                    continue

                model_path = os.path.join(manufacturer_path, model_dir)
                if not os.path.exists(model_path):
                    _LOGGER.error("Model directory %s should be there but is not!", model_path)
                    continue

                model = model_dir.lower()

                model_json_path = os.path.join(model_path, "model.json")
                if not os.path.exists(model_json_path):
                    # QUESTION: raise error?
                    _LOGGER.warning("model.json should exist in %s!", model_path)
                    continue

                if library.get(manufacturer) is None:
                    library[manufacturer] = {}

                library[manufacturer].update({model: {"path": model_path}})

                model_json = await self._hass.async_add_executor_job(_load_json)  # type: ignore

                if model_json.get("device_type"):
                    library[manufacturer][model].update(
                        {"device_type": model_json.get("device_type")},
                    )

                aliases = model_json.get("aliases")
                if aliases:
                    for alias in aliases:
                        library[manufacturer].update({alias.lower(): {"path": model_path}})

                        if model_json.get("device_type"):
                            library[manufacturer][alias.lower()].update(
                                {"device_type": model_json.get("device_type")},
                            )

        return library
