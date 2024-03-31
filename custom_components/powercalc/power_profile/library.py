from __future__ import annotations

import logging
import os
import re
from typing import NamedTuple

from homeassistant.core import HomeAssistant

from custom_components.powercalc.aliases import MANUFACTURER_DIRECTORY_MAPPING
from custom_components.powercalc.const import DATA_PROFILE_LIBRARY, DOMAIN

from .loader.local import LocalLoader
from .loader.remote import RemoteLoader
from .power_profile import DOMAIN_DEVICE_TYPE, PowerProfile

BUILT_IN_DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../data")
CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"

_LOGGER = logging.getLogger(__name__)


class ProfileLibrary:
    def __init__(self, hass: HomeAssistant) -> None:
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
        self._loader = LocalLoader(hass)
        #self._loader = RemoteLoader(hass)
        self._profiles: dict[str, list[PowerProfile]] = {}
        self._manufacturer_models: dict[str, list] | None = None
        self._manufacturer_device_types: dict[str, list] = {}

    async def initialize(self) -> None:
        await self._loader.initialize()

    @staticmethod
    async def factory(hass: HomeAssistant) -> ProfileLibrary:
        """Creates and loads the profile library
        Makes sure it is only loaded once and instance is saved in hass data registry.
        """
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}

        if DATA_PROFILE_LIBRARY in hass.data[DOMAIN]:
            return hass.data[DOMAIN][DATA_PROFILE_LIBRARY]  # type: ignore

        library = ProfileLibrary(hass)
        await library.initialize()
        hass.data[DOMAIN][DATA_PROFILE_LIBRARY] = library
        return library

    async def get_manufacturer_listing(self, entity_domain: str | None = None) -> list[str]:
        """Get listing of available manufacturers."""

        device_type = DOMAIN_DEVICE_TYPE.get(entity_domain) if entity_domain else None
        manufacturers = await self._loader.get_manufacturer_listing(device_type)
        return sorted(manufacturers)

    async def get_model_listing(self, manufacturer: str) -> list[str]:
        """Get listing of available models for a given manufacturer."""
        cached_models = self._manufacturer_models.get(manufacturer)
        if cached_models:
            return cached_models
        models = await self._loader.get_model_listing(manufacturer)
        self._manufacturer_models[manufacturer] = sorted(models)
        return self._manufacturer_models[manufacturer]

    async def get_profile(
        self,
        model_info: ModelInfo,
        custom_directory: str | None = None,
    ) -> PowerProfile | None:
        """Get a power profile for a given manufacturer and model."""
        # Support multiple LUT in subdirectories
        sub_profile = None
        if "/" in model_info.model:
            (model, sub_profile) = model_info.model.split("/", 1)
            model_info = ModelInfo(model_info.manufacturer, model)

        profile = None
        if custom_directory:
            profile = await self.create_power_profile(model_info, custom_directory)
        else:
            profile = await self.create_power_profile(model_info)
            # profiles = await self.get_profiles_by_manufacturer(model_info.manufacturer)
            # for p in profiles:
            #     if p.supports(model_info.model):
            #         profile = p
            #         break

        if not profile:
            return None

        if sub_profile:
            profile.select_sub_profile(sub_profile)

        return profile

    async def get_profiles_by_manufacturer(
        self,
        manufacturer: str,
    ) -> list[PowerProfile]:
        """Lazy loads a list of power profiles per manufacturer.

        Using the following lookup fallback mechanism:
         - check in user defined directory (config/powercalc-custom-models)
         - check in alternative user defined directory (config/custom_components/powercalc/custom_data)
         - check in built-in directory (config/custom_components/powercalc/data)
        """
        if manufacturer in MANUFACTURER_DIRECTORY_MAPPING:
            manufacturer = str(MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer))
        manufacturer = manufacturer.lower()

        if manufacturer in self._profiles:
            return self._profiles[manufacturer]

        profiles = []
        models = await self._loader.get_model_listing(manufacturer)
        for model in models:
            power_profile = await self.create_power_profile(
                ModelInfo(manufacturer, model),
            )
            if power_profile is None:  # pragma: no cover
                continue

            profiles.append(power_profile)

        self._profiles[manufacturer] = profiles
        return profiles

    async def create_power_profile(
        self,
        model_info: ModelInfo,
        custom_directory: str | None = None,
    ) -> PowerProfile | None:
        """Create a power profile object from the model JSON data."""

        try:
            model = model_info.model
            if not custom_directory:
                model = await self.find_model(model_info)
                if not model:
                    return None

            json_data, directory = await self._loader.load_model(model_info.manufacturer, model, custom_directory)
        except FileNotFoundError:
            #_LOGGER.error("model.json file not found for %s/%s", model_info.manufacturer, model_info.model)
            return None

        if not json_data:
            return None
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

        return profile

    async def find_model(self, model_info: ModelInfo) -> str | None:
        """Check whether this power profile supports a given model ID.
        Also looks at possible aliases.
        """

        model = model_info.model
        search = {
            model,
            model.lower(),
            model.lower().replace("#slash#", "/"),
            re.sub(r"\(([^\(\)]+)\)$", "$1", model),
        }

        return await self._loader.find_model(model_info.manufacturer, search)

class ModelInfo(NamedTuple):
    manufacturer: str
    model: str
