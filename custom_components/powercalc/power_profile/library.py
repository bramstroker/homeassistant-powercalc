from __future__ import annotations

import logging
import os
import re
from typing import NamedTuple

from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_DISABLE_LIBRARY_DOWNLOAD, DATA_PROFILE_LIBRARY, DOMAIN, DOMAIN_CONFIG

from .error import LibraryError
from .loader.composite import CompositeLoader
from .loader.local import LocalLoader
from .loader.protocol import Loader
from .loader.remote import RemoteLoader
from .power_profile import DOMAIN_DEVICE_TYPE, PowerProfile

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
    async def factory(hass: HomeAssistant) -> ProfileLibrary:
        """Creates and loads the profile library
        Makes sure it is only loaded once and instance is saved in hass data registry.
        """
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}

        if DATA_PROFILE_LIBRARY in hass.data[DOMAIN]:
            return hass.data[DOMAIN][DATA_PROFILE_LIBRARY]  # type: ignore

        library = ProfileLibrary(hass, ProfileLibrary.create_loader(hass))
        await library.initialize()
        hass.data[DOMAIN][DATA_PROFILE_LIBRARY] = library
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

        global_config = hass.data[DOMAIN].get(DOMAIN_CONFIG, {})
        disable_library_download: bool = bool(global_config.get(CONF_DISABLE_LIBRARY_DOWNLOAD, False))
        if not disable_library_download:
            loaders.append(RemoteLoader(hass))

        return CompositeLoader(loaders)

    async def get_manufacturer_listing(self, entity_domain: str | None = None) -> list[str]:
        """Get listing of available manufacturers."""
        device_type = DOMAIN_DEVICE_TYPE.get(entity_domain) if entity_domain else None
        manufacturers = await self._loader.get_manufacturer_listing(device_type)
        return sorted(manufacturers)

    async def get_model_listing(self, manufacturer: str, entity_domain: str | None = None) -> list[str]:
        """Get listing of available models for a given manufacturer."""

        resolved_manufacturer = await self._loader.find_manufacturer(manufacturer)
        if not resolved_manufacturer:
            return []
        device_type = DOMAIN_DEVICE_TYPE.get(entity_domain) if entity_domain else None
        cache_key = f"{resolved_manufacturer}/{device_type}"
        cached_models = self._manufacturer_models.get(cache_key)
        if cached_models:
            return cached_models
        models = await self._loader.get_model_listing(resolved_manufacturer, device_type)
        self._manufacturer_models[cache_key] = sorted(models)
        return self._manufacturer_models[cache_key]

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
            model_info = ModelInfo(model_info.manufacturer, model, model_info.model_id)

        profile = await self.create_power_profile(model_info, custom_directory)

        if not profile:
            return None

        if sub_profile:
            await profile.select_sub_profile(sub_profile)

        return profile

    async def create_power_profile(
        self,
        model_info: ModelInfo,
        custom_directory: str | None = None,
    ) -> PowerProfile | None:
        """Create a power profile object from the model JSON data."""

        try:
            manufacturer = await self._resolve_manufacturer(model_info, custom_directory)
            if not manufacturer:
                return None

            model = await self._resolve_model(manufacturer, model_info, custom_directory)
            if not model:
                return None

            json_data, directory = await self._load_model_data(manufacturer, model, custom_directory)
            if linked_profile := json_data.get("linked_lut"):
                linked_manufacturer, linked_model = linked_profile.split("/")
                _, directory = await self._load_model_data(linked_manufacturer, linked_model, custom_directory)

        except LibraryError as e:
            _LOGGER.error("Problem loading model: %s", e)
            return None

        return await self._create_power_profile_instance(manufacturer, model, directory, json_data)

    async def _resolve_manufacturer(self, model_info: ModelInfo, custom_directory: str | None) -> str | None:
        """Resolve the manufacturer, either from the model info or by loading it."""
        if custom_directory:
            return model_info.manufacturer
        return await self._loader.find_manufacturer(model_info.manufacturer)

    async def _resolve_model(self, manufacturer: str, model_info: ModelInfo, custom_directory: str | None) -> str | None:
        """Resolve the model identifier, searching for it if no custom directory is provided."""
        if custom_directory:
            return model_info.model_id or model_info.model

        for model_identifier in (model_info.model_id, model_info.model):
            if model_identifier:
                resolved_model = await self.find_model(manufacturer, model_identifier)
                if resolved_model:
                    return resolved_model

        return None

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

    async def find_model(self, manufacturer: str, model: str) -> str | None:
        """Check whether this power profile supports a given model ID.
        Also looks at possible aliases.
        """

        search = {
            model,
            model.replace("#slash#", "/"),
            model.lower(),
            model.lower().replace("#slash#", "/"),
            re.sub(r"^(.*)\(([^()]+)\)$", r"\2", model),
        }

        return await self._loader.find_model(manufacturer, search)

    def get_loader(self) -> Loader:
        return self._loader


class ModelInfo(NamedTuple):
    manufacturer: str
    model: str
    # Starting from HA 2024.8 we can use model_id to identify the model
    model_id: str | None = None
