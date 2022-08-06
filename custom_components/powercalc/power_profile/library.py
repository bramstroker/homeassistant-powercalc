from __future__ import annotations

import os
import json

from typing import NamedTuple

from homeassistant.core import HomeAssistant

from .power_profile import PowerProfile

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
        self._profiles: dict[str, list[PowerProfile]] = dict()

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

    def get_profile(self, model_info: ModelInfo, custom_directory: str | None = None) -> PowerProfile | None:
        """Get a power profile for a given manufacturer and model"""
        if custom_directory:
            return self._create_power_profile(model_info, custom_directory)

        profiles = self.get_profiles_by_manufacturer(model_info.manufacturer)
        for profile in profiles:
            if profile.supports(model_info.model):
                return profile
        return None

    def get_profiles_by_manufacturer(self, manufacturer: str) -> list[PowerProfile]:
        """
        Lazy loads a list of power profiles per manufacturer

        Using the following lookup fallback mechanism:
         - check in user defined directory (config/powercalc-custom-models)
         - check in alternative user defined directory (config/custom_components/powercalc/custom_data)
         - check in buildin directory (config/custom_components/powercalc/data)
        """

        if manufacturer in MANUFACTURER_DIRECTORY_MAPPING:
            manufacturer = MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer)
        manufacturer = manufacturer.lower()
        
        if manufacturer in self._profiles:
            return self._profiles[manufacturer]

        profiles = []
        for data_dir in self._data_directories:
            manufacturer_dir = os.path.join(data_dir, manufacturer)
            if not os.path.exists(manufacturer_dir):
                continue
            for model in os.listdir(manufacturer_dir):
                if model.startswith('.'):
                    continue
                profiles.append(
                    self._create_power_profile(
                        ModelInfo(manufacturer, model),
                        os.path.join(manufacturer_dir, model)
                    )
                )
        
        self._profiles[manufacturer] = profiles
        return profiles

    def _create_power_profile(self, model_info: ModelInfo, directory: str) -> PowerProfile:
        model_json_path = os.path.join(directory, 'model.json')
        with open(model_json_path) as file:
            json_data = json.load(file)
            profile = PowerProfile(
                self._hass,
                manufacturer=model_info.manufacturer,
                model=model_info.model,
                directory=directory,
                json_data=json_data
            )
        return profile

class ModelInfo(NamedTuple):
    manufacturer: str
    model: str