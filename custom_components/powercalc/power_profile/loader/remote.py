import json
import logging
import os
import time
from typing import Any, cast

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.powercalc.helpers import get_library_json_path
from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

_LOGGER = logging.getLogger(__name__)

DOWNLOAD_PROXY = "https://powercalc.lauwbier.nl/api"
ENDPOINT_LIBRARY = f"{DOWNLOAD_PROXY}/library"
ENDPOINT_DOWNLOAD = f"{DOWNLOAD_PROXY}/download"


class RemoteLoader(Loader):
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.library_contents: dict = {}
        self.model_infos: dict[str, dict] = {}
        self.manufacturer_models: dict[str, list[dict]] = {}

    async def initialize(self) -> None:
        self.library_contents = await self.load_library_json()

        # Load contents of library JSON into memory
        manufacturers: list[dict] = self.library_contents.get("manufacturers", [])
        for manufacturer in manufacturers:
            models: list[dict] = manufacturer.get("models", [])
            for model in models:
                manufacturer_name = str(manufacturer.get("name"))
                model_id = str(model.get("id"))
                self.model_infos[f"{manufacturer_name}/{model_id}"] = model
                if manufacturer_name not in self.manufacturer_models:
                    self.manufacturer_models[manufacturer_name] = []
                self.manufacturer_models[manufacturer_name].append(model)

    @staticmethod
    async def load_library_json() -> dict[str, Any]:
        """Load library.json file"""

        async with aiohttp.ClientSession() as session, session.get(ENDPOINT_LIBRARY) as resp:
            if resp.status != 200:
                _LOGGER.error("Failed to download library.json from github, falling back to local copy")
                with open(get_library_json_path()) as f:
                    return cast(dict[str, Any], json.load(f))
            return cast(dict[str, Any], await resp.json())

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""

        return {
            manufacturer["name"] for manufacturer
            in self.library_contents.get("manufacturers", [])
            if not device_type or device_type in manufacturer.get("device_types", [])
        }

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        return {
            model["id"] for model
            in self.manufacturer_models.get(manufacturer, [])
            if not device_type or device_type in model.get("device_type", DeviceType.LIGHT)
        }

    async def load_model(self, manufacturer: str, model: str) -> tuple[dict, str] | None:
        model_info = self.model_infos.get(f"{manufacturer}/{model}")
        if not model_info:
            raise LibraryLoadingError("Model not found in library: %s/%s", manufacturer, model)

        storage_path = self.get_storage_path(manufacturer, model)

        needs_update = False
        path_exists = os.path.exists(storage_path)
        if not path_exists:
            needs_update = True

        if path_exists:
            remote_modification_time = model_info.get("update_timestamp", time.time())
            local_modification_time = self._get_local_modification_time(storage_path)
            if remote_modification_time > local_modification_time:
                _LOGGER.debug("Remote profile is newer than local profile")
                needs_update = True

        if needs_update:
            try:
                await self.download_profile(manufacturer, model, storage_path)
            except ProfileDownloadError as e:
                if not path_exists:
                    raise e
                _LOGGER.error("Failed to download profile, falling back to local profile")

        model_path = os.path.join(storage_path, "model.json")

        with open(model_path) as f:
            json_data = json.load(f)

        return json_data, storage_path

    def get_storage_path(self, manufacturer: str, model: str) -> str:
        return str(self.hass.config.path(STORAGE_DIR, "powercalc_profiles", manufacturer, model))

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        """Find the model in the library."""

        models = self.manufacturer_models.get(manufacturer, [])
        if not models:
            return None

        return next((model.get("id") for model in models for string in search
                     if string == model.get("id") or string in model.get("aliases", [])), None)

    @staticmethod
    def _get_local_modification_time(folder: str) -> float:
        """Get the latest modification time of the local profile directory."""
        times = [os.path.getmtime(os.path.join(folder, f)) for f in os.listdir(folder)]
        times.sort(reverse=True)
        return times[0] if times else 0

    async def download_profile(self, manufacturer: str, model: str, storage_path: str) -> None:
        """
        Download the profile from Github using the Powercalc download API
        Saves the profile to manufacturer/model directory in .storage/powercalc_profiles folder
        """

        _LOGGER.info("Downloading profile: %s/%s from github", manufacturer, model)

        endpoint = f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}"

        def _save_file(data: bytes, directory: str) -> None:
            """Save file from Github to local storage directory"""
            path = os.path.join(storage_path, directory)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(endpoint) as resp:
                    if resp.status != 200:
                        raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}")
                    resources = await resp.json()

                await self.hass.async_add_executor_job(lambda: os.makedirs(storage_path, exist_ok=True))  # type: ignore

                # Download the files
                for resource in resources:
                    url = resource.get("url")
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise ProfileDownloadError(f"Failed to download github URL: {url}")

                        contents = await resp.read()
                        await self.hass.async_add_executor_job(_save_file, contents, resource.get("path"))  # type: ignore
            except aiohttp.ClientError as e:
                raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}") from e

