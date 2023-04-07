from __future__ import annotations

import json
import logging
import os
from typing import NamedTuple

from homeassistant.core import HomeAssistant

from ..aliases import MANUFACTURER_DIRECTORY_MAPPING
from ..const import DATA_PROFILE_LIBRARY, DOMAIN
from .power_profile import DEVICE_DOMAINS, PowerProfile

BUILT_IN_DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../data")
CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"

_LOGGER = logging.getLogger(__name__)


class ProfileLibrary:
    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._data_directories: list[str] = [
            d
            for d in (
                os.path.join(hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
                os.path.join(os.path.dirname(__file__), "../custom_data"),
                BUILT_IN_DATA_DIRECTORY,
            )
            if os.path.exists(d)
        ]
        self._profiles: dict[str, list[PowerProfile]] = {}
        self._manufacturer_device_types: dict[str, list] | None = None

    def factory(hass: HomeAssistant) -> ProfileLibrary:
        """
        Creates and loads the profile library
        Makes sure it is only loaded once and instance is saved in hass data registry
        """
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}

        if DATA_PROFILE_LIBRARY in hass.data[DOMAIN]:
            return hass.data[DOMAIN][DATA_PROFILE_LIBRARY]

        library = ProfileLibrary(hass)
        hass.data[DOMAIN][DATA_PROFILE_LIBRARY] = library
        return library

    factory = staticmethod(factory)

    def get_manufacturer_listing(self, entity_domain: str | None = None) -> list[str]:
        """
        Get listing of available manufacturers

        @param entity_domain   Only return manufacturers providing profiles for a given domain
        """

        if self._manufacturer_device_types is None:
            with open(
                os.path.join(BUILT_IN_DATA_DIRECTORY, "manufacturer_device_types.json"),
                "r",
            ) as file:
                self._manufacturer_device_types = json.load(file)

        manufacturers: list[str] = []
        for data_dir in self._data_directories:
            for manufacturer in next(os.walk(data_dir))[1]:
                if (
                    entity_domain
                    and data_dir == BUILT_IN_DATA_DIRECTORY
                    and len(
                        [
                            device_type
                            for device_type in self._manufacturer_device_types.get(
                                manufacturer
                            )
                            or []
                            if DEVICE_DOMAINS[device_type] == entity_domain
                        ]
                    )
                    == 0
                ):
                    continue

                manufacturers.append(manufacturer)
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

    async def get_profile(
        self, model_info: ModelInfo, custom_directory: str | None = None
    ) -> PowerProfile | None:
        """Get a power profile for a given manufacturer and model"""

        # Support multiple LUT in subdirectories
        sub_profile = None
        if "/" in model_info.model:
            (model, sub_profile) = model_info.model.split("/", 1)
            model_info = ModelInfo(model_info.manufacturer, model)

        profile = None
        if custom_directory:
            profile = await self._create_power_profile(model_info, custom_directory)
        else:
            profiles = await self.get_profiles_by_manufacturer(model_info.manufacturer)
            for p in profiles:
                if p.supports(model_info.model):
                    profile = p
                    break

        if not profile:
            return None

        if sub_profile:
            profile.select_sub_profile(sub_profile)

        return profile

    async def get_profiles_by_manufacturer(
        self, manufacturer: str
    ) -> list[PowerProfile]:
        """
        Lazy loads a list of power profiles per manufacturer

        Using the following lookup fallback mechanism:
         - check in user defined directory (config/powercalc-custom-models)
         - check in alternative user defined directory (config/custom_components/powercalc/custom_data)
         - check in built-in directory (config/custom_components/powercalc/data)
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
            for model in next(os.walk(manufacturer_dir))[1]:
                if model[0] in [".", "@"]:
                    continue
                power_profile = await self._create_power_profile(
                    ModelInfo(manufacturer, model),
                    os.path.join(manufacturer_dir, model),
                )
                if power_profile is None:  # pragma: no cover
                    continue

                profiles.append(power_profile)

        self._profiles[manufacturer] = profiles
        return profiles

    async def _create_power_profile(
        self, model_info: ModelInfo, directory: str
    ) -> PowerProfile | None:
        """Create a power profile object from the model JSON data"""
        model_json_path = os.path.join(directory, "model.json")
        try:
            with open(model_json_path) as file:
                json_data = json.load(file)
                profile = PowerProfile(
                    self._hass,
                    manufacturer=model_info.manufacturer,
                    model=model_info.model,
                    directory=directory,
                    json_data=json_data,
                )
                # When the power profile supplies multiple sub profiles we select one by default
                if not profile.sub_profile and profile.sub_profile_select:
                    profile.select_sub_profile(profile.sub_profile_select.default)

        except FileNotFoundError:
            _LOGGER.error("model.json file not found in directory %s", directory)
            return None

        return profile


class ModelInfo(NamedTuple):
    manufacturer: str
    model: str
