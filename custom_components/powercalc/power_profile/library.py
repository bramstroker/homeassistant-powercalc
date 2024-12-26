from __future__ import annotations

import logging
import os
import re
from typing import NamedTuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers.singleton import singleton

from custom_components.powercalc.const import CONF_DISABLE_LIBRARY_DOWNLOAD, DOMAIN, DOMAIN_CONFIG

from .error import LibraryError
from .loader.composite import CompositeLoader
from .loader.local import LocalLoader
from .loader.protocol import Loader
from .loader.remote import RemoteLoader
from .power_profile import PowerProfile, get_device_types_from_domain

LEGACY_CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"
CUSTOM_DATA_DIRECTORY = "powercalc/profiles"

_LOGGER = logging.getLogger(__name__)


class ProfileLibrary:
    def __init__(self, hass: HomeAssistant, loader: Loader) -> None:
        self._hass = hass
        self._loader = loader
        self._profiles: dict[str, list[PowerProfile]] = {}
        self._manufacturer_models: dict[str, list[str]] = {}
        self._manufacturer_device_types: dict[str, list] = {}

    async def initialize(self) -> None:
        await self._loader.initialize()

    @staticmethod
    @singleton("powercalc_library")
    async def factory(hass: HomeAssistant) -> ProfileLibrary:
        """Creates and loads the profile library
        Makes sure it is only loaded once and instance is saved in hass data registry.
        """
        library = ProfileLibrary(hass, ProfileLibrary.create_loader(hass))
        await library.initialize()
        return library

    @staticmethod
    def create_loader(hass: HomeAssistant) -> Loader:
        loaders: list[Loader] = [
            LocalLoader(hass, data_dir)
            for data_dir in [
                os.path.join(hass.config.config_dir, LEGACY_CUSTOM_DATA_DIRECTORY),
                os.path.join(hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
                os.path.join(os.path.dirname(__file__), "../custom_data"),
            ]
            if os.path.exists(data_dir)
        ]

        domain_config = hass.data.get(DOMAIN, {})
        global_config = domain_config.get(DOMAIN_CONFIG, {})
        disable_library_download: bool = bool(global_config.get(CONF_DISABLE_LIBRARY_DOWNLOAD, False))
        if not disable_library_download:
            loaders.append(RemoteLoader(hass))

        return CompositeLoader(loaders)

    async def get_manufacturer_listing(self, entity_domain: str | None = None) -> list[str]:
        """Get listing of available manufacturers."""

        device_types = get_device_types_from_domain(entity_domain) if entity_domain else None
        manufacturers = await self._loader.get_manufacturer_listing(device_types)
        return sorted(manufacturers)

    async def get_model_listing(self, manufacturer: str, entity_domain: str | None = None) -> list[str]:
        """Get listing of available models for a given manufacturer."""

        resolved_manufacturers = await self._loader.find_manufacturers(manufacturer)
        if not resolved_manufacturers:
            return []
        device_types = get_device_types_from_domain(entity_domain) if entity_domain else None
        all_models: list[str] = []
        for manufacturer in resolved_manufacturers:
            cache_key = f"{manufacturer}/{device_types}"
            cached_models = self._manufacturer_models.get(cache_key)
            if cached_models:
                all_models.extend(cached_models)
                continue
            models = await self._loader.get_model_listing(manufacturer, device_types)
            self._manufacturer_models[cache_key] = sorted(models)
            all_models.extend(models)

        return all_models

    async def get_profile(
        self,
        model_info: ModelInfo,
        custom_directory: str | None = None,
    ) -> PowerProfile:
        """Get a power profile for a given manufacturer and model."""
        # Support multiple LUT in subdirectories
        sub_profile = None
        if "/" in model_info.model:
            (model, sub_profile) = model_info.model.split("/", 1)
            model_info = ModelInfo(model_info.manufacturer, model, model_info.model_id)

        profile = await self.create_power_profile(model_info, custom_directory)

        if sub_profile:
            await profile.select_sub_profile(sub_profile)

        return profile

    async def create_power_profile(
        self,
        model_info: ModelInfo,
        custom_directory: str | None = None,
    ) -> PowerProfile:
        """Create a power profile object from the model JSON data."""

        if not custom_directory:
            models = await self.find_models(model_info)
            if not models:
                raise LibraryError(f"Model {model_info.manufacturer} {model_info.model} not found")
            model_info = next(iter(models))

        json_data, directory = await self._load_model_data(model_info.manufacturer, model_info.model, custom_directory)
        if linked_profile := json_data.get("linked_lut"):
            linked_manufacturer, linked_model = linked_profile.split("/")
            _, directory = await self._load_model_data(linked_manufacturer, linked_model, custom_directory)

        return await self._create_power_profile_instance(model_info.manufacturer, model_info.model, directory, json_data)

    async def find_manufacturers(self, model_info: ModelInfo) -> set[str]:
        """Resolve the manufacturer, either from the model info or by loading it."""
        return await self._loader.find_manufacturers(model_info.manufacturer)

    async def find_models(self, model_info: ModelInfo) -> set[ModelInfo]:
        """Resolve the model identifier, searching for it if no custom directory is provided."""
        search: set[str] = set()
        for model_identifier in (model_info.model_id, model_info.model):
            if model_identifier:
                model_identifier = model_identifier.replace("#slash#", "/")
                search.update(
                    {
                        model_identifier,
                        model_identifier.lower(),
                        re.sub(r"^(.*)\(([^()]+)\)$", r"\2", model_identifier),
                    },
                )
                if "/" in model_identifier:
                    search.update(model_identifier.split("/"))

        manufacturers = await self._loader.find_manufacturers(model_info.manufacturer)
        found_models: set[ModelInfo] = set()
        if not manufacturers:
            return found_models

        for manufacturer in manufacturers:
            models = await self._loader.find_model(manufacturer, search)
            if models:
                found_models.update(ModelInfo(manufacturer, model) for model in models)

        return found_models

    async def _load_model_data(self, manufacturer: str, model: str, custom_directory: str | None) -> tuple[dict, str]:
        """Load the model data from the appropriate directory."""
        loader = LocalLoader(self._hass, custom_directory, is_custom_directory=True) if custom_directory else self._loader
        result = await loader.load_model(manufacturer, model)
        if not result:
            raise LibraryError(f"Model {manufacturer} {model} not found")

        return result

    async def _create_power_profile_instance(self, manufacturer: str, model: str, directory: str, json_data: dict) -> PowerProfile:
        """Create and initialize the PowerProfile object."""
        profile = PowerProfile(
            self._hass,
            manufacturer=manufacturer,
            model=model,
            directory=directory,
            json_data=json_data,
        )

        if not profile.sub_profile and profile.sub_profile_select:
            await profile.select_sub_profile(profile.sub_profile_select.default)

        return profile

    def get_loader(self) -> Loader:
        return self._loader


class ModelInfo(NamedTuple):
    manufacturer: str
    model: str
    # Starting from HA 2024.8 we can use model_id to identify the model
    model_id: str | None = None
