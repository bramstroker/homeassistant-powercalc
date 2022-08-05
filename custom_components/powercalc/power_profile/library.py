from __future__ import annotations

import os
import glob
import json

from typing import NamedTuple
from types import MappingProxyType

from homeassistant.core import HomeAssistant

from ..const import DATA_PROFILE_LIBRARY, DOMAIN
from ..aliases import MANUFACTURER_DIRECTORY_MAPPING, MODEL_DIRECTORY_MAPPING

CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"


class ProfileLibrary:
    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._data_directories: list[str] = [
            dir
            for dir in (
                os.path.join(hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
                os.path.join(os.path.dirname(__file__), "../custom_data"),
                os.path.join(os.path.dirname(__file__), "../data"),
            )
            if os.path.exists(dir)
        ]
        self._model_aliases: MappingProxyType[str, list[ModelAlias]] | None = None

    def factory(hass: HomeAssistant) -> ProfileLibrary:
        """
        Creates and loads the profile library
        Makes sure it is only loaded once and instance is save in hass data registry
        """
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}
        
        if DATA_PROFILE_LIBRARY in hass.data[DOMAIN]:
            return hass.data[DOMAIN][DATA_PROFILE_LIBRARY]
        
        library = ProfileLibrary(hass)
        hass.data[DOMAIN][DATA_PROFILE_LIBRARY] = library
        return library
    
    factory = staticmethod(factory)

    def get_manufacturer_listing(self) -> list[str]:
        """Get listing of available manufacturers"""
        manufacturers: list[str] = []
        for data_dir in self._data_directories:
            manufacturers.extend(next(os.walk(data_dir))[1])
        return sorted(manufacturers)

    def get_model_listing(self, manufacturer: str) -> list[str]:
        """Get listing of available models for a given manufacturer"""
        models: list[str] = []
        for data_dir in self._data_directories:
            manufacturer_dir = os.path.join(data_dir, manufacturer)
            if not os.path.exists(manufacturer_dir):
                continue
            models.extend(os.listdir(manufacturer_dir))
        return sorted(models)

    def get_model_directory(self, manufacturer: str, model: str) -> str | None:
        """Get a directory for a model, walk through the available data directories"""
    
        manufacturer_directory = (
            MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer) or manufacturer
        ).lower()

        for data_dir in self._data_directories:
            for model_directory in self.get_possible_matching_models(manufacturer, manufacturer_directory, model):
                directory = os.path.join(data_dir, manufacturer_directory, model_directory)
                if os.path.exists(directory):
                    return directory
        return None

    def get_possible_matching_models(self, manufacturer: str, manufacturer_directory: str, model: str) -> list[str]:
        if self._model_aliases is None:
            self._model_aliases = self.load_model_aliases()

        models = [model]

        if isinstance(
            MODEL_DIRECTORY_MAPPING.get(manufacturer), dict
        ) and MODEL_DIRECTORY_MAPPING.get(manufacturer).get(model):
            models.append(MODEL_DIRECTORY_MAPPING.get(manufacturer).get(model))
        

        model_aliases = self._model_aliases.get(manufacturer_directory) or []
        for alias in model_aliases:
            # matching logic
            if alias.alias == model:
                models.append(alias.model)
        
        return models
    
    def load_model_aliases(self) -> MappingProxyType[str, list[ModelAlias]]:
        aliases = dict()
        for dir in self._data_directories:
            for file_path in glob.glob(dir + "/**/model.json", recursive=True):
                with open(file_path) as file:
                    json_data = json.load(file)
                    continue
                
        return MappingProxyType(
            {
                "ikea": [
                    ModelAlias("L1527", "FLOALT panel WS 30x30")
                ]
            }
        )

class ModelAlias(NamedTuple):
    model: str
    alias: str