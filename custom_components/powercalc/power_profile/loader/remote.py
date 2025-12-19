import asyncio
from collections.abc import Callable, Coroutine
from functools import partial
import json
from json import JSONDecodeError
import logging
import os
import shutil
from typing import Any, NotRequired, TypedDict, cast

import aiohttp
from aiohttp import ClientError
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.powercalc.const import API_URL
from custom_components.powercalc.helpers import async_cache
from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

_LOGGER = logging.getLogger(__name__)

ENDPOINT_LIBRARY = f"{API_URL}/library"
ENDPOINT_DOWNLOAD = f"{API_URL}/download"

TIMEOUT_SECONDS = 30


class LibraryModel(TypedDict):
    id: str
    aliases: NotRequired[list[str]]
    hash: str
    device_type: NotRequired[DeviceType]


class LibraryManufacturer(TypedDict):
    name: str
    aliases: NotRequired[list[str]]
    models: list[LibraryModel]


class RemoteLoader(Loader):
    retry_timeout = 3

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.library_contents: dict = {}
        self.model_infos: dict[str, LibraryModel] = {}
        self.manufacturer_models: dict[str, list[LibraryModel]] = {}
        self.model_lookup: dict[str, dict[str, list[LibraryModel]]] = {}
        self.manufacturer_lookup: dict[str, set[str]] = {}
        self.profile_hashes: dict[str, str] = {}

    async def initialize(self) -> None:
        """Initialize the loader."""

        self.library_contents = await self.load_library_json()

        self.profile_hashes = await self.hass.async_add_executor_job(self.load_profile_hashes)

        self.model_infos.clear()
        self.model_lookup.clear()
        self.manufacturer_models.clear()
        self.manufacturer_lookup.clear()

        # Load contents of library JSON into several dictionaries for easy access
        manufacturers: list[LibraryManufacturer] = self.library_contents.get("manufacturers", [])

        for manufacturer in manufacturers:
            manufacturer_name = str(manufacturer.get("dir_name"))
            models = manufacturer.get("models", [])

            # Store model info and group models by manufacturer
            self.model_infos.update({f"{manufacturer_name}/{model.get('id')!s}": model for model in models})
            self.manufacturer_models[manufacturer_name] = models

            model_lookup: dict[str, list[LibraryModel]] = {}
            for model in models:
                model_id = str(model.get("id")).lower()

                # Exact match → append first (high priority)
                bucket = model_lookup.setdefault(model_id, [])
                bucket.append(model)

                # Aliases → append after (lower priority)
                for alias in model.get("aliases", []):
                    bucket_alias = model_lookup.setdefault(alias.lower(), [])
                    # Only append if it's not the exact-id bucket
                    if bucket_alias is bucket:
                        # alias == id → ignore, already added
                        continue
                    bucket_alias.append(model)

            self.model_lookup[manufacturer_name] = model_lookup

            # Map manufacturer aliases
            self.manufacturer_lookup[manufacturer_name.lower()] = {manufacturer_name}
            for alias in manufacturer.get("aliases", []):
                self.manufacturer_lookup.setdefault(alias.lower(), set()).add(manufacturer_name)

    async def load_library_json(self) -> dict[str, Any]:
        """Load library.json file"""

        local_path = self.hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json")

        def _load_local_library_json() -> dict[str, Any]:
            """Load library.json file from local storage"""
            if not os.path.exists(local_path):
                raise ProfileDownloadError("Local library.json file not found")
            with open(local_path) as f:
                return cast(dict[str, Any], json.load(f))

        async def _download_remote_library_json() -> dict[str, Any] | None:
            """
            Download library.json from Github.
            If download is successful, save it to local storage to use as fallback in case of internet connection issues.
            """
            _LOGGER.debug("Loading library.json from github")

            session = async_get_clientsession(self.hass)

            try:
                async with async_timeout.timeout(TIMEOUT_SECONDS), session.get(ENDPOINT_LIBRARY) as resp:
                    if resp.status != 200:
                        raise ProfileDownloadError(
                            f"Failed to download library.json, unexpected status code: {resp.status}",
                        )

                    data = await resp.read()

            except (TimeoutError, ClientError) as err:
                raise ProfileDownloadError(f"Failed to download library.json: {err}") from err

            def _save_to_local_storage(data: bytes) -> None:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(data)

            await self.hass.async_add_executor_job(_save_to_local_storage, data)

            return cast(dict[str, Any], json.loads(data))

        try:
            return cast(dict[str, Any], await self.download_with_retry(_download_remote_library_json))
        except ProfileDownloadError:
            _LOGGER.debug("Failed to download library.json, falling back to local copy")
            return await self.hass.async_add_executor_job(_load_local_library_json)

    @async_cache
    async def get_manufacturer_listing(self, device_types: set[DeviceType] | None) -> set[tuple[str, str]]:
        """Get listing of available manufacturers."""

        return {
            (manufacturer["dir_name"], manufacturer["full_name"])
            for manufacturer in self.library_contents.get("manufacturers", [])
            if not device_types or any(device_type in manufacturer.get("device_types", []) for device_type in device_types)
        }

    @async_cache
    async def find_manufacturers(self, search: str) -> set[str]:
        """Find the manufacturer in the library."""
        return self.manufacturer_lookup.get(search, set())

    @async_cache
    async def get_model_listing(self, manufacturer: str, device_types: set[DeviceType] | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        models = self.manufacturer_models.get(manufacturer)
        if not models:
            return set()

        return {
            model["id"]
            for model in self.manufacturer_models.get(manufacturer, [])
            if not device_types or any(device_type in model.get("device_type", [DeviceType.LIGHT]) for device_type in device_types)
        }

    @async_cache
    async def find_model(self, manufacturer: str, search: set[str]) -> list[str]:
        """Find matching model IDs in the library."""
        models = self.model_lookup.get(manufacturer, {})
        return [model["id"] for phrase in search if (phrase_lower := phrase.lower()) in models for model in models[phrase_lower]]

    @async_cache
    async def load_model(
        self,
        manufacturer: str,
        model: str,
        force_update: bool = False,
        retry_count: int = 0,
    ) -> tuple[dict, str] | None:
        """Load a model, downloading it if necessary, with retry logic."""
        model_info = self._get_library_model(manufacturer, model)
        storage_path = self.get_storage_path(manufacturer, model)
        model_path = os.path.join(storage_path, "model.json")

        if await self._needs_update(model_info, manufacturer, model, model_path, force_update):
            await self._download_profile_with_retry(manufacturer, model, storage_path, model_path)

        try:
            json_data = await self._load_model_json(model_path)
        except JSONDecodeError as e:
            return await self._handle_json_decode_error(e, manufacturer, model, retry_count)

        return json_data, storage_path

    def _get_library_model(self, manufacturer: str, model: str) -> LibraryModel:
        """Retrieve model info, or raise an error if not found."""
        model_info = self.model_infos.get(f"{manufacturer}/{model}")
        if not model_info:
            raise LibraryLoadingError("Model not found in library: %s/%s", manufacturer, model)
        return model_info

    async def _needs_update(self, model_info: LibraryModel, manufacturer: str, model: str, model_path: str, force_update: bool) -> bool:
        """Check if the model needs to be updated."""
        if force_update:
            return True

        path_exists = os.path.exists(model_path)
        if not path_exists:
            return True

        existing_hash = self.profile_hashes.get(f"{manufacturer}/{model}")
        new_hash = model_info.get("hash")
        return existing_hash != new_hash

    async def _download_profile_with_retry(self, manufacturer: str, model: str, storage_path: str, model_path: str) -> None:
        """Attempt to download the profile, with retry logic and error handling."""
        try:
            callback = partial(self.download_profile, manufacturer, model, storage_path)
            await self.download_with_retry(callback)
            model_info = self._get_library_model(manufacturer, model)
            self.profile_hashes[f"{manufacturer}/{model}"] = str(model_info.get("hash"))
            await self.hass.async_add_executor_job(self.write_profile_hashes, self.profile_hashes)
        except ProfileDownloadError as e:
            if not os.path.exists(model_path):
                await self.hass.async_add_executor_job(shutil.rmtree, storage_path)
                raise e
            _LOGGER.debug("Failed to download profile, falling back to local profile")

    async def _load_model_json(self, model_path: str) -> dict:
        """Load the JSON data from the model file."""

        def _load_json() -> dict[str, Any]:
            with open(model_path) as f:
                return cast(dict[str, Any], json.load(f))

        return await self.hass.async_add_executor_job(_load_json)

    async def _handle_json_decode_error(
        self,
        error: JSONDecodeError,
        manufacturer: str,
        model: str,
        retry_count: int,
    ) -> tuple[dict, str] | None:
        """Handle JSON decode errors with retry logic."""
        _LOGGER.error("model.json file is not valid JSON for manufacturer: %s, model: %s", manufacturer, model)
        if retry_count < 2:
            _LOGGER.debug("Retrying to load model.json file")
            return await self.load_model(manufacturer, model, True, retry_count + 1)
        raise LibraryLoadingError("Failed to load model.json file") from error

    def get_storage_path(self, manufacturer: str, model: str) -> str:
        """Retrieve the storage path for a given manufacturer and model."""
        return str(self.hass.config.path(STORAGE_DIR, "powercalc_profiles", manufacturer, model))

    async def download_with_retry(self, callback: Callable[[], Coroutine[Any, Any, None | dict[str, Any]]]) -> None | dict[str, Any]:
        """Download a file from a remote endpoint with retries"""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                return await callback()
            except (ClientError, TimeoutError, ProfileDownloadError) as e:
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

        session = async_get_clientsession(self.hass)

        try:
            async with async_timeout.timeout(TIMEOUT_SECONDS):
                async with session.get(endpoint) as resp:
                    if resp.status != 200:
                        raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}")
                    resources = await resp.json()

                await self.hass.async_add_executor_job(lambda: os.makedirs(storage_path, exist_ok=True))

                # Download the files
                for resource in resources:
                    url = resource.get("url")
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise ProfileDownloadError(f"Failed to download github URL: {url}")

                        contents = await resp.read()
                        await self.hass.async_add_executor_job(_save_file, contents, resource.get("path"))
        except (TimeoutError, aiohttp.ClientError) as e:
            raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}") from e

    def load_profile_hashes(self) -> dict[str, str]:
        """Load profile hashes from local storage"""

        path = self.hass.config.path(STORAGE_DIR, "powercalc_profiles", ".profile_hashes")
        if not os.path.exists(path):
            return {}

        with open(path) as f:
            return json.load(f)  # type: ignore

    def write_profile_hashes(self, hashes: dict[str, str]) -> None:
        """Write profile hashes to local storage"""

        path = self.hass.config.path(STORAGE_DIR, "powercalc_profiles", ".profile_hashes")
        with open(path, "w") as json_file:
            json.dump(hashes, json_file, indent=4)
