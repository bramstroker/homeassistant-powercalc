import asyncio
import datetime
import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Coroutine
from functools import partial
from json import JSONDecodeError
from typing import Any, cast

import aiohttp
from aiohttp import ClientError
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
    retry_timeout = 3

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.library_contents: dict = {}
        self.model_infos: dict[str, dict] = {}
        self.manufacturer_models: dict[str, list[dict]] = {}
        self.last_update_time: float | None = None

    async def initialize(self) -> None:
        self.library_contents = await self.load_library_json()
        self.last_update_time = await self.hass.async_add_executor_job(self.get_last_update_time)  # type: ignore

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

    async def load_library_json(self) -> dict[str, Any]:
        """Load library.json file"""

        def _load_local_library_json() -> dict[str, Any]:
            """Load library.json file from local storage"""
            with open(get_library_json_path()) as f:
                return cast(dict[str, Any], json.load(f))

        async def _download_remote_library_json() -> dict[str, Any] | None:
            """Download library.json from github"""
            _LOGGER.debug("Loading library.json from github")
            async with aiohttp.ClientSession() as session, session.get(ENDPOINT_LIBRARY) as resp:
                if resp.status != 200:
                    raise ProfileDownloadError("Failed to download library.json, unexpected status code")
                return cast(dict[str, Any], await resp.json())

        try:
            return cast(dict[str, Any], await self.download_with_retry(_download_remote_library_json))
        except ProfileDownloadError:
            _LOGGER.debug("Failed to download library.json, falling back to local copy")
            return await self.hass.async_add_executor_job(_load_local_library_json)  # type: ignore

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""

        return {
            manufacturer["name"]
            for manufacturer in self.library_contents.get("manufacturers", [])
            if not device_type or device_type in manufacturer.get("device_types", [])
        }

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        return {
            model["id"]
            for model in self.manufacturer_models.get(manufacturer, [])
            if not device_type or device_type in model.get("device_type", DeviceType.LIGHT)
        }

    async def load_model(
        self,
        manufacturer: str,
        model: str,
        force_update: bool = False,
        retry_count: int = 0,
    ) -> tuple[dict, str] | None:
        model_info = self.model_infos.get(f"{manufacturer}/{model}")
        if not model_info:
            raise LibraryLoadingError("Model not found in library: %s/%s", manufacturer, model)

        storage_path = self.get_storage_path(manufacturer, model)
        model_path = os.path.join(storage_path, "model.json")

        needs_update = False
        path_exists = os.path.exists(model_path)
        if not path_exists:
            needs_update = True

        if path_exists:
            remote_modification_time = self._get_remote_modification_time(model_info)
            if self.last_update_time and remote_modification_time > self.last_update_time:
                _LOGGER.debug("Remote profile is newer than local profile")
                needs_update = True

        if needs_update or force_update:
            try:
                callback = partial(self.download_profile, manufacturer, model, storage_path)
                await self.download_with_retry(callback)
                await self.set_last_update_time(time.time())
            except ProfileDownloadError as e:
                if not path_exists:
                    await self.hass.async_add_executor_job(shutil.rmtree, storage_path)
                    raise e
                _LOGGER.debug("Failed to download profile, falling back to local profile")

        def _load_json() -> dict[str, Any]:
            """Load model.json file for a given model."""
            with open(model_path) as f:
                return cast(dict[str, Any], json.load(f))

        try:
            json_data = await self.hass.async_add_executor_job(_load_json)  # type: ignore
        except JSONDecodeError as e:
            _LOGGER.error("model.json file is not valid JSON")
            if retry_count < 2:
                _LOGGER.debug("Retrying to load model.json file")
                return await self.load_model(manufacturer, model, True, retry_count + 1)
            raise LibraryLoadingError("Failed to load model.json file") from e

        return json_data, storage_path

    def get_storage_path(self, manufacturer: str, model: str) -> str:
        return str(self.hass.config.path(STORAGE_DIR, "powercalc_profiles", manufacturer, model))

    def get_last_update_time(self) -> float | None:
        """Get the last update time of the local library"""
        path = self.hass.config.path(STORAGE_DIR, "powercalc_profiles", ".last_update")
        if not os.path.exists(path):
            return None

        with open(path) as f:
            return float(f.read())

    async def set_last_update_time(self, time: float) -> None:
        """Set the last update time of the local library"""
        self.last_update_time = time
        path = self.hass.config.path(STORAGE_DIR, "powercalc_profiles", ".last_update")

        def _write() -> None:
            """Write last update time to file"""
            with open(path, "w") as f:
                f.write(str(time))

        return await self.hass.async_add_executor_job(_write)  # type: ignore

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        """Find the model in the library."""

        models = self.manufacturer_models.get(manufacturer, [])
        if not models:
            return None

        return next(
            (model.get("id") for model in models for string in search if string == model.get("id") or string in model.get("aliases", [])),
            None,
        )

    @staticmethod
    def _get_remote_modification_time(model_info: dict) -> float:
        remote_modification_time = model_info.get("updated_at", time.time())
        if isinstance(remote_modification_time, str):
            remote_modification_time = datetime.datetime.fromisoformat(remote_modification_time).timestamp()
        return remote_modification_time  # type: ignore

    async def download_with_retry(self, callback: Callable[[], Coroutine[Any, Any, None | dict[str, Any]]]) -> None | dict[str, Any]:
        """Download a file from a remote endpoint with retries"""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                return await callback()
            except (ClientError, ProfileDownloadError) as e:
                _LOGGER.debug(e)
                retry_count += 1
                if retry_count == max_retries:
                    raise ProfileDownloadError(f"Failed to download even after {max_retries} retries, falling back to local copy") from e

                await asyncio.sleep(self.retry_timeout)
                _LOGGER.warning("Failed to download, retrying... (Attempt %d of %d)", retry_count + 1, max_retries)
        return None  # pragma: no cover

    async def download_profile(self, manufacturer: str, model: str, storage_path: str) -> None:
        """
        Download the profile from Github using the Powercalc download API
        Saves the profile to manufacturer/model directory in .storage/powercalc_profiles folder
        """

        _LOGGER.debug("Downloading profile: %s/%s from github", manufacturer, model)

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
