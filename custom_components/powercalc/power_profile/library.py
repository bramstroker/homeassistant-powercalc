from __future__ import annotations

import json
import os
import re
from typing import Any, NamedTuple, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.singleton import singleton

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_DISABLE_LIBRARY_DOWNLOAD, DOMAIN, DOMAIN_CONFIG
from custom_components.powercalc.helpers import (
    build_related_entity_placeholder_not_found_message,
    collect_placeholders,
    iter_related_entity_placeholders,
    replace_placeholders,
    resolve_related_entity_placeholder,
)

from .error import LibraryError
from .loader.composite import CompositeLoader
from .loader.local import LocalLoader
from .loader.protocol import Loader
from .loader.remote import RemoteLoader
from .power_profile import DeviceType, DiscoveryBy, PowerProfile

LEGACY_CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"
CUSTOM_DATA_DIRECTORY = "powercalc/profiles"


def load_sub_profile_data(base_dir: str) -> list[tuple[str, dict[str, Any]]]:
    """Load sub-profile JSON blobs from disk."""
    sub_dirs = next(os.walk(base_dir))[1]
    result = []
    for sub_dir in sub_dirs:
        json_path = os.path.join(base_dir, sub_dir, "model.json")
        if os.path.isfile(json_path):
            with open(json_path, encoding="utf-8") as f:
                json_data = cast(dict[str, Any], json.load(f))
        else:
            json_data = {}
        result.append((sub_dir, json_data))
    return sorted(result, key=lambda item: item[0])


class ProfileLibrary:
    def __init__(self, hass: HomeAssistant, loader: Loader) -> None:
        self._hass = hass
        self._loader = loader
        self._profiles: dict[str, list[PowerProfile]] = {}
        self._manufacturer_models: dict[str, set[tuple[str, str]]] = {}
        self._manufacturer_device_types: dict[str, list] = {}

    async def initialize(self) -> None:
        await self._loader.initialize()

    @staticmethod
    @singleton("powercalc_library")
    async def factory(hass: HomeAssistant) -> ProfileLibrary:
        """
        Creates and loads the profile library.
        Make sure we have a single instance throughout the application.
        """
        library = ProfileLibrary(hass, ProfileLibrary.create_loader(hass))
        await library.initialize()
        return library

    @staticmethod
    def create_loader(hass: HomeAssistant, skip_remote_loader: bool = False) -> Loader:
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
        if not disable_library_download and not skip_remote_loader:
            loaders.append(RemoteLoader(hass))

        return CompositeLoader(loaders)

    async def get_manufacturer_listing(
        self,
        device_types: set[DeviceType] | None = None,
        discovery_by: DiscoveryBy | None = None,
    ) -> list[tuple[str, str]]:
        """Get listing of available manufacturers."""
        manufacturers = await self._loader.get_manufacturer_listing(device_types, discovery_by)
        return sorted(manufacturers)

    async def get_model_listing(
        self,
        manufacturer: str,
        device_types: set[DeviceType] | None = None,
        discovery_by: DiscoveryBy | None = None,
    ) -> list[tuple[str, str]]:
        """Get listing of available models and display names for a given manufacturer."""

        resolved_manufacturers = await self._loader.find_manufacturers(manufacturer)
        if not resolved_manufacturers:
            return []

        all_models: list[tuple[str, str]] = []
        for manufacturer in resolved_manufacturers:
            cache_key = f"{manufacturer}/{device_types}/{discovery_by}"
            cached_models = self._manufacturer_models.get(cache_key)
            if cached_models:
                all_models.extend(sorted(cached_models))
                continue
            models = await self._loader.get_model_listing(manufacturer, device_types, discovery_by)
            self._manufacturer_models[cache_key] = models
            all_models.extend(sorted(models))

        return sorted(all_models, key=lambda model: model[0])

    async def get_profile(
        self,
        model_info: ModelInfo,
        source_entity: SourceEntity | None = None,
        custom_directory: str | None = None,
        variables: dict[str, str] | None = None,
        process_variables: bool = True,
    ) -> PowerProfile:
        """Get a power profile for a given manufacturer and model."""
        # Support multiple LUT in subdirectories
        sub_profile = None
        if "/" in model_info.model:
            (model, sub_profile) = model_info.model.split("/", 1)
            model_info = ModelInfo(model_info.manufacturer, model, model_info.model_id)

        if not custom_directory:
            models = await self.find_models(model_info)
            if not models:
                raise LibraryError(f"Model {model_info.manufacturer} {model_info.model} not found")
            model_info = next(iter(models))

        profile = await self.create_power_profile(
            model_info,
            source_entity,
            custom_directory,
            variables,
            process_variables,
        )

        if sub_profile:
            await profile.select_sub_profile(sub_profile)

        return profile

    async def create_power_profile(
        self,
        model_info: ModelInfo,
        source_entity: SourceEntity | None = None,
        custom_directory: str | None = None,
        variables: dict[str, str] | None = None,
        process_variables: bool = True,
    ) -> PowerProfile:
        """Create a power profile object from the model JSON data."""

        json_data, directory = await self._load_model_data(model_info.manufacturer, model_info.model, custom_directory)
        json_data = self._process_profile_json(json_data, variables or {}, source_entity, process_variables)

        if linked_profile := json_data.get("linked_profile", json_data.get("linked_lut")):
            linked_manufacturer, linked_model = linked_profile.split("/")
            linked_json_data, directory = await self._load_model_data(
                linked_manufacturer,
                linked_model,
                custom_directory,
            )
            json_data.update(linked_json_data)

        raw_sub_profiles = await self._hass.async_add_executor_job(load_sub_profile_data, directory)
        sub_profiles = [
            (
                sub_dir,
                self._process_profile_json(sub_profile_json, variables or {}, source_entity, process_variables),
            )
            for sub_dir, sub_profile_json in raw_sub_profiles
        ]

        return await self._create_power_profile_instance(
            model_info.manufacturer,
            model_info.model,
            directory,
            json_data,
            sub_profiles,
        )

    def _process_profile_json(
        self,
        json_data: dict[str, Any],
        variables: dict[str, str],
        source_entity: SourceEntity | None,
        process_variables: bool,
    ) -> dict[str, Any]:
        # json_data is potentially retrieved from cache, so we need to copy it to avoid modifying the cache
        json_data = json_data.copy()
        if not process_variables:
            return json_data

        if json_data.get("fields"):  # When custom fields in profile are defined, make sure all variables are passed
            self.validate_variables(json_data, variables)

        placeholders = collect_placeholders(json_data)
        replacements = self.compute_replacement_variables(placeholders, variables.copy(), source_entity)
        return cast(dict[str, Any], replace_placeholders(json_data, replacements))

    def compute_replacement_variables(
        self,
        placeholders: set[str],
        variables: dict[str, str],
        source_entity: SourceEntity | None,
    ) -> dict[str, str]:
        variables = variables or {}

        if source_entity:
            if "entity" in placeholders:
                variables["entity"] = source_entity.entity_id

            for placeholder in iter_related_entity_placeholders(placeholders):
                related_entity = resolve_related_entity_placeholder(
                    self._hass,
                    placeholder,
                    source_entity=source_entity,
                )
                if not related_entity:
                    raise LibraryError(
                        build_related_entity_placeholder_not_found_message(placeholder, source_entity.entity_id),
                    )
                variables[placeholder] = related_entity

        return variables

    @staticmethod
    def validate_variables(json_data: dict[str, Any], variables: dict[str, str]) -> None:
        fields = json_data.get("fields", {}).keys()

        # Check if all variables are valid for the model
        for variable in variables:
            if variable not in fields and variable != "entity":
                raise LibraryError(f"Variable {variable} is not valid for this model")

        # Check if all fields have corresponding variables
        missing_fields = [field for field in fields if field not in variables]
        if missing_fields:
            raise LibraryError(f"Missing variables for fields: {', '.join(missing_fields)}")

    async def find_manufacturers(self, manufacturer: str) -> set[str]:
        """Resolve the manufacturer, either from the model info or by loading it."""
        return await self._loader.find_manufacturers(manufacturer)

    async def find_models(self, model_info: ModelInfo) -> list[ModelInfo]:
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
        if not manufacturers:
            return []

        found_models: list[ModelInfo] = []
        for manufacturer in manufacturers:
            models = await self._loader.find_model(manufacturer, search)
            if models:
                found_models.extend(ModelInfo(manufacturer, model) for model in models)

        return list(dict.fromkeys(found_models))

    async def find_model_migration(self, model_info: ModelInfo) -> ModelInfo | None:
        """Resolve a legacy canonical model id to its replacement using library metadata."""
        manufacturers = await self._loader.find_manufacturers(model_info.manufacturer)
        if not manufacturers:
            return None

        matches: set[ModelInfo] = set()
        for manufacturer in manufacturers:
            migrated_model = await self._loader.find_model_migration(manufacturer, model_info.model)
            if migrated_model:
                matches.add(ModelInfo(manufacturer, migrated_model))

        if len(matches) != 1:
            return None

        return next(iter(matches))

    async def _load_model_data(self, manufacturer: str, model: str, custom_directory: str | None) -> tuple[dict, str]:
        """Load the model data from the appropriate directory."""
        loader = (
            LocalLoader(self._hass, custom_directory, is_custom_directory=True) if custom_directory else self._loader
        )
        result = await loader.load_model(manufacturer, model)
        if not result:
            raise LibraryError(f"Model {manufacturer} {model} not found")

        return result

    async def _create_power_profile_instance(
        self,
        manufacturer: str,
        model: str,
        directory: str,
        json_data: dict,
        sub_profiles: list[tuple[str, dict]] | None = None,
    ) -> PowerProfile:
        """Create and initialize the PowerProfile object."""
        profile = PowerProfile(
            self._hass,
            manufacturer=manufacturer,
            model=model,
            directory=directory,
            json_data=json_data,
            sub_profiles=sub_profiles,
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
