import asyncio
from collections.abc import Callable, Coroutine
from functools import partial
import json
from json import JSONDecodeError
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, NotRequired, TypedDict, cast
from urllib.parse import urlsplit

import aiohttp
from aiohttp import ClientError
from awesomeversion import AwesomeVersion
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.loader import async_get_integration

from custom_components.powercalc.const import (
    API_URL,
    BUILT_IN_LIBRARY_DIR,
    DOMAIN,
    LIBRARY_DISCOVERY_LOW_PRIORITY_DOMAINS,
)
from custom_components.powercalc.helpers import async_cache, clear_async_cache
from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.loader.protocol import Loader, ModelMetadata
from custom_components.powercalc.power_profile.power_profile import DeviceType, DiscoveryBy

_LOGGER = logging.getLogger(__name__)

ENDPOINT_LIBRARY = f"{API_URL}/library"
ENDPOINT_DOWNLOAD = f"{API_URL}/download"

TIMEOUT_SECONDS = 30
MODEL_JSON_RETRY_LIMIT = 2

ALLOWED_RESOURCE_HOSTS = frozenset({"github.com", "raw.githubusercontent.com"})


def _validate_resource_url(url: object) -> str:
    """Validate that a resource URL points to an allowed HTTPS host."""
    if not isinstance(url, str):
        raise ProfileDownloadError("Remote profile resource has an invalid URL")

    try:
        parsed_url = urlsplit(url)
        is_allowed = (
            parsed_url.scheme == "https"
            and parsed_url.hostname in ALLOWED_RESOURCE_HOSTS
            and parsed_url.username is None
            and parsed_url.password is None
            and parsed_url.port in (None, 443)
        )
    except ValueError as err:
        raise ProfileDownloadError(f"Remote profile resource has an invalid URL: {url}") from err

    if not is_allowed:
        raise ProfileDownloadError(f"Remote profile resource URL is not allowed: {url}")
    return url


def _resolve_resource_path(storage_path: str, resource_path: object) -> Path:
    """Resolve and validate a resource path within the profile storage directory."""
    if not isinstance(resource_path, str) or not resource_path or "\0" in resource_path:
        raise ProfileDownloadError("Remote profile resource has an invalid path")

    relative_path = Path(resource_path)
    if relative_path.is_absolute():
        raise ProfileDownloadError(f"Remote profile resource path is not allowed: {resource_path}")

    try:
        storage_directory = Path(storage_path).resolve()
        destination = (storage_directory / relative_path).resolve()
    except (OSError, ValueError) as err:
        raise ProfileDownloadError(f"Remote profile resource has an invalid path: {resource_path}") from err
    if destination == storage_directory or not destination.is_relative_to(storage_directory):
        raise ProfileDownloadError(f"Remote profile resource path is not allowed: {resource_path}")
    return destination


def _validate_resources(resources: object, storage_path: str) -> list[tuple[str, Path]]:
    """Validate all resources in a remote profile response."""
    if not isinstance(resources, list) or not all(isinstance(resource, dict) for resource in resources):
        raise ProfileDownloadError("Remote profile response contains invalid resources")

    return [
        (_validate_resource_url(resource.get("url")), _resolve_resource_path(storage_path, resource.get("path")))
        for resource in resources
    ]


def _sync_directory(directory: Path) -> None:
    """Persist a directory entry, so a completed rename survives an unclean shutdown."""
    try:
        directory_descriptor = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - directories cannot be opened on all platforms
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:  # pragma: no cover - directory fsync is not supported on all platforms
        pass
    finally:
        os.close(directory_descriptor)


def _save_resource(data: bytes, path: Path) -> None:
    """Atomically save a downloaded resource to the local profile storage directory.

    The contents are flushed to disk before the rename, and the directory entry is flushed
    after it. Without both, a power loss shortly after an update can leave the new file name
    pointing at unwritten data, which is how a cached profile ends up as invalid JSON.
    """
    os.makedirs(path.parent, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as file_handle:
            file_handle.write(data)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, path)
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _save_resources(resources: list[tuple[bytes, Path]]) -> None:
    """Save all downloaded resources after every response has completed successfully."""
    for data, path in resources:
        _save_resource(data, path)


class LibraryModel(TypedDict):
    id: str
    name: NotRequired[str]
    aliases: NotRequired[list[str]]
    legacy_ids: NotRequired[list[str]]
    hash: str
    device_type: NotRequired[DeviceType]
    discovery_by: NotRequired[DiscoveryBy]
    min_version: NotRequired[str]


class LibraryManufacturer(TypedDict):
    name: str
    dir_name: str
    aliases: NotRequired[list[str]]
    models: list[LibraryModel]


class RemoteLoader(Loader):
    retry_timeout = 3

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.library_contents: dict[str, Any] = {}
        self.model_infos: dict[str, LibraryModel] = {}
        self.manufacturer_models: dict[str, list[LibraryModel]] = {}
        self.model_lookup: dict[str, dict[str, list[LibraryModel]]] = {}
        self.manufacturer_lookup: dict[str, set[str]] = {}
        self.profile_hashes: dict[str, str] = {}
        self._model_load_locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def initialize(self, prefer_cached: bool = False) -> None:
        """Initialize the loader.

        Pass `prefer_cached` to keep the network off the critical path, using the library.json
        already in local storage when there is one. Only the very first run has to download.
        """

        integration = await async_get_integration(self.hass, DOMAIN)
        powercalc_version = AwesomeVersion(str(integration.version))

        self._clear_caches()
        self.library_contents = await self.load_library_json(prefer_cached)
        self.profile_hashes = await self.hass.async_add_executor_job(self._load_profile_hashes)

        self.model_infos.clear()
        self.model_lookup.clear()
        self.manufacturer_models.clear()
        self.manufacturer_lookup.clear()

        manufacturers: list[LibraryManufacturer] = self.library_contents.get("manufacturers", [])

        for manufacturer in manufacturers:
            self._index_manufacturer(manufacturer, powercalc_version)

    def get_discovery_low_priority_domains(self) -> set[str]:
        """Get the low priority discovery integration domains declared by library metadata."""
        return set(self.library_contents.get(LIBRARY_DISCOVERY_LOW_PRIORITY_DOMAINS, []))

    def _index_manufacturer(self, manufacturer: LibraryManufacturer, powercalc_version: AwesomeVersion) -> None:
        """Register a manufacturer, its aliases and all of its supported models in the lookup tables."""
        manufacturer_name = str(manufacturer.get("dir_name"))
        models: list[LibraryModel] = manufacturer.get("models", []) or []

        # manufacturer alias map (alias -> {canonical manufacturer_name})
        self.manufacturer_lookup.setdefault(manufacturer_name.lower(), set()).add(manufacturer_name)
        for alias in manufacturer.get("aliases", []) or []:
            self.manufacturer_lookup.setdefault(str(alias).lower(), set()).add(manufacturer_name)

        # per-manufacturer model lookup
        kept_models: list[LibraryModel] = []
        lookup: dict[str, list[LibraryModel]] = {}

        for model in models:
            model_id = str(model.get("id"))
            self.model_infos[f"{manufacturer_name}/{model_id}"] = model

            if self._is_unsupported_version(manufacturer_name, model_id, model, powercalc_version):
                continue

            kept_models.append(model)
            self._add_model_to_lookup(lookup, model, model_id.lower())

        self.manufacturer_models[manufacturer_name] = kept_models
        self.model_lookup[manufacturer_name] = lookup

    @staticmethod
    def _is_unsupported_version(
        manufacturer_name: str,
        model_id: str,
        model: LibraryModel,
        powercalc_version: AwesomeVersion,
    ) -> bool:
        """Check whether the model requires a newer powercalc version than the one installed."""
        min_version = model.get("min_version")
        if not min_version or powercalc_version >= AwesomeVersion(min_version):
            return False

        _LOGGER.debug(
            "Skipping model %s/%s as it requires powercalc version %s (current: %s)",
            manufacturer_name,
            model_id,
            min_version,
            powercalc_version,
        )
        return True

    @staticmethod
    def _add_model_to_lookup(lookup: dict[str, list[LibraryModel]], model: LibraryModel, model_id_lower: str) -> None:
        """Bucket a model by its id and aliases. Exact ids take priority over aliases."""
        # Exact id bucket first (highest priority)
        lookup.setdefault(model_id_lower, []).insert(0, model)

        # Alias buckets afterwards (lower priority)
        for alias in model.get("aliases", []) or []:
            alias_lower = str(alias).lower()
            if alias_lower == model_id_lower:
                continue
            # Append to the end to ensure aliased models are always last
            lookup.setdefault(alias_lower, []).append(model)

    def _clear_caches(self) -> None:
        """Clear cached lookups backed by mutable library state."""
        clear_async_cache(self.get_manufacturer_listing)
        clear_async_cache(self.find_manufacturers)
        clear_async_cache(self.get_model_listing)
        clear_async_cache(self.find_model)
        clear_async_cache(self.find_model_migration)
        clear_async_cache(self.load_model)

    async def load_library_json(self, prefer_cached: bool = False) -> dict[str, Any]:
        """Load library.json, from local storage or from the download API.

        With `prefer_cached` the locally stored copy wins when it exists, so the caller never
        waits on the network. The periodic library update refreshes it later.
        """
        if prefer_cached:
            cached_library = await self.hass.async_add_executor_job(self._read_local_library_json)
            if cached_library is not None:
                _LOGGER.debug("Loaded library.json from local storage")
                return cached_library
            _LOGGER.debug("No library.json in local storage yet, downloading it")

        try:
            return cast(dict[str, Any], await self.download_with_retry(self._download_remote_library_json))
        except ProfileDownloadError:
            _LOGGER.debug("Failed to download library.json, falling back to local copy")
            return await self.hass.async_add_executor_job(self._load_local_library_json)

    def _get_library_json_path(self) -> str:
        """Retrieve the local storage path for the library.json file."""
        return str(self.hass.config.path(STORAGE_DIR, BUILT_IN_LIBRARY_DIR, "library.json"))

    def _read_local_library_json(self) -> dict[str, Any] | None:
        """Read library.json from local storage, None when it is missing or unusable.

        A truncated or unreadable copy is reported as absent rather than raised, so the caller
        falls through to a fresh download instead of failing setup on every restart.
        """
        local_path = self._get_library_json_path()
        if not os.path.exists(local_path):
            return None
        try:
            with open(local_path) as f:
                return cast(dict[str, Any], json.load(f))
        except (JSONDecodeError, OSError) as err:
            _LOGGER.warning("Local library.json is unusable (%s), discarding it and downloading a fresh copy", err)
            return None

    def _load_local_library_json(self) -> dict[str, Any]:
        """Load library.json from local storage, raising when it is not usable."""
        library_json = self._read_local_library_json()
        if library_json is None:
            raise ProfileDownloadError("Local library.json file not found or unusable")
        return library_json

    async def _download_remote_library_json(self) -> dict[str, Any] | None:
        """
        Download library.json from Github.
        On success, save it to local storage as a fallback for internet connection issues.
        """
        _LOGGER.debug("Loading library.json from github")

        local_path = self._get_library_json_path()
        session = async_get_clientsession(self.hass)

        try:
            async with asyncio.timeout(TIMEOUT_SECONDS), session.get(ENDPOINT_LIBRARY) as resp:
                if resp.status != 200:
                    raise ProfileDownloadError(
                        f"Failed to download library.json, unexpected status code: {resp.status}",
                    )

                data = await resp.read()

        except (TimeoutError, ClientError) as err:
            raise ProfileDownloadError(f"Failed to download library.json: {err}") from err

        await self.hass.async_add_executor_job(_save_resource, data, Path(local_path))

        return cast(dict[str, Any], json.loads(data))

    @async_cache
    async def get_manufacturer_listing(
        self,
        device_types: set[DeviceType] | None,
        discovery_by: DiscoveryBy | None = None,
    ) -> set[tuple[str, str]]:
        """Get listing of available manufacturers."""

        return {
            (manufacturer["dir_name"], manufacturer["full_name"])
            for manufacturer in self.library_contents.get("manufacturers", [])
            if any(
                self._model_matches_filters(model, device_types, discovery_by)
                # Use the indexed models, so models requiring a newer Powercalc version are left out here as well.
                for model in self.manufacturer_models.get(str(manufacturer.get("dir_name")), [])
            )
        }

    @async_cache
    async def find_manufacturers(self, search: str) -> set[str]:
        """Find the manufacturer in the library."""
        return self.manufacturer_lookup.get(search.lower(), set())

    @async_cache
    async def get_model_listing(
        self,
        manufacturer: str,
        device_types: set[DeviceType] | None,
        discovery_by: DiscoveryBy | None = None,
    ) -> set[tuple[str, str]]:
        """Get listing of available models and display names for a given manufacturer."""
        models = self.manufacturer_models.get(manufacturer)
        if not models:
            return set()

        return {
            (model["id"], str(model.get("name") or model["id"]))
            for model in self.manufacturer_models.get(manufacturer, [])
            if self._model_matches_filters(model, device_types, discovery_by)
        }

    @staticmethod
    def _model_matches_filters(
        model: LibraryModel,
        device_types: set[DeviceType] | None,
        discovery_by: DiscoveryBy | None,
    ) -> bool:
        """Check whether an indexed model passes the requested filters.

        Device types and discovery modes this Powercalc version does not know about are treated
        as a non match, so profiles using a newly introduced value never break the listings.
        """
        try:
            model_device_type = DeviceType(model.get("device_type", DeviceType.LIGHT))
            model_discovery_by = DiscoveryBy(model.get("discovery_by", DiscoveryBy.ENTITY))
        except ValueError:
            return False

        if device_types and model_device_type not in device_types:
            return False

        return not discovery_by or model_discovery_by == discovery_by

    @async_cache
    async def find_model(self, manufacturer: str, search: set[str]) -> list[str]:
        """Find matching model IDs in the library."""
        models = self.model_lookup.get(manufacturer, {})
        return [
            model["id"]
            for phrase in search
            if (phrase_lower := phrase.lower()) in models
            for model in models[phrase_lower]
        ]

    @async_cache
    async def find_model_migration(self, manufacturer: str, model: str) -> str | None:
        """Find the canonical model id for a legacy profile id."""
        model_lower = model.lower()
        matches = {
            str(model_data.get("id"))
            for manufacturer_data in self.library_contents.get("manufacturers", [])
            if str(manufacturer_data.get("dir_name", "")).lower() == manufacturer
            for model_data in manufacturer_data.get("models", []) or []
            if model_lower in {str(legacy_id).lower() for legacy_id in model_data.get("legacy_ids", []) or []}
        }

        if len(matches) != 1:
            return None

        return next(iter(matches))

    async def get_model_metadata(self, manufacturer: str, model: str) -> ModelMetadata | None:
        """Return discovery metadata straight from the library index, without downloading the profile."""
        model_info = self.model_infos.get(f"{manufacturer}/{model}")
        if not model_info:
            return None

        try:
            device_type = DeviceType(model_info.get("device_type", DeviceType.LIGHT))
            discovery_by = DiscoveryBy(model_info.get("discovery_by", DiscoveryBy.ENTITY))
        except ValueError:
            return None

        return ModelMetadata(device_type=device_type, discovery_by=discovery_by)

    @async_cache
    async def load_model(
        self,
        manufacturer: str,
        model: str,
        force_update: bool = False,
        retry_count: int = 0,
    ) -> tuple[dict[str, Any], str] | None:
        """Load a model, downloading it if necessary, with retry logic."""
        lock = self._model_load_locks.setdefault((manufacturer, model), asyncio.Lock())
        async with lock:
            return await self._load_model_locked(manufacturer, model, force_update, retry_count)

    async def _load_model_locked(
        self,
        manufacturer: str,
        model: str,
        force_update: bool,
        retry_count: int,
    ) -> tuple[dict[str, Any], str] | None:
        """Load a model while holding its per-profile lock."""
        model_info = self._get_library_model(manufacturer, model)
        storage_path = self.get_storage_path(manufacturer, model)
        model_path = os.path.join(storage_path, "model.json")

        while True:
            if await self._needs_update(model_info, manufacturer, model, model_path, force_update):
                await self._download_profile_with_retry(manufacturer, model, storage_path, model_path)

            try:
                json_data = await self._load_model_json(model_path)
            except JSONDecodeError as error:
                if retry_count >= MODEL_JSON_RETRY_LIMIT:
                    _LOGGER.error(
                        "model.json remains invalid after %d redownload attempts for manufacturer: %s, model: %s",
                        MODEL_JSON_RETRY_LIMIT,
                        manufacturer,
                        model,
                    )
                    raise LibraryLoadingError("Failed to load model.json file") from error

                retry_count += 1
                force_update = True
                _LOGGER.warning(
                    "model.json is not valid JSON for manufacturer: %s, model: %s; redownloading profile "
                    "(attempt %d of %d)",
                    manufacturer,
                    model,
                    retry_count,
                    MODEL_JSON_RETRY_LIMIT,
                )
                continue

            return json_data, storage_path

    def _get_library_model(self, manufacturer: str, model: str) -> LibraryModel:
        """Retrieve model info, or raise an error if not found."""
        model_info = self.model_infos.get(f"{manufacturer}/{model}")
        if not model_info:
            raise LibraryLoadingError(f"Model not found in library: {manufacturer}/{model}")
        return model_info

    async def _needs_update(
        self,
        model_info: LibraryModel,
        manufacturer: str,
        model: str,
        model_path: str,
        force_update: bool,
    ) -> bool:
        """Check if the model needs to be updated."""
        if force_update:
            return True

        path_exists = await self.hass.async_add_executor_job(os.path.exists, model_path)
        if not path_exists:
            return True

        existing_hash = self.profile_hashes.get(f"{manufacturer}/{model}")
        new_hash = model_info.get("hash")
        return existing_hash != new_hash

    async def _download_profile_with_retry(
        self,
        manufacturer: str,
        model: str,
        storage_path: str,
        model_path: str,
    ) -> None:
        """Attempt to download the profile, with retry logic and error handling."""
        try:
            model_info = self._get_library_model(manufacturer, model)
            model_hash = str(model_info.get("hash"))
            callback = partial(self.download_profile, manufacturer, model, storage_path, model_hash)
            await self.download_with_retry(callback)
            self.profile_hashes[f"{manufacturer}/{model}"] = model_hash
            await self.hass.async_add_executor_job(self._write_profile_hashes, dict(self.profile_hashes))
        except ProfileDownloadError as e:
            path_exists, storage_path_exists = await self.hass.async_add_executor_job(
                self._profile_paths_exist,
                model_path,
                storage_path,
            )
            if not path_exists:
                if storage_path_exists:
                    await self.hass.async_add_executor_job(shutil.rmtree, storage_path)  # pragma: no cover
                raise e
            _LOGGER.debug("Failed to download profile, falling back to local profile")

    @staticmethod
    def _profile_paths_exist(model_path: str, storage_path: str) -> tuple[bool, bool]:
        """Check profile paths from the executor."""
        return os.path.exists(model_path), os.path.exists(storage_path)

    async def _load_model_json(self, model_path: str) -> dict[str, Any]:
        """Load the JSON data from the model file."""

        def _load_json() -> dict[str, Any]:
            with open(model_path) as f:
                return cast(dict[str, Any], json.load(f))

        return await self.hass.async_add_executor_job(_load_json)

    def get_storage_path(self, manufacturer: str, model: str) -> str:
        """Retrieve the storage path for a given manufacturer and model."""
        return str(self.hass.config.path(STORAGE_DIR, BUILT_IN_LIBRARY_DIR, manufacturer, model))

    async def download_with_retry(
        self,
        callback: Callable[[], Coroutine[Any, Any, dict[str, Any] | None]],
    ) -> dict[str, Any] | None:
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
                    raise ProfileDownloadError(
                        f"Failed to download even after {max_retries} retries, falling back to local copy",
                    ) from e

                await asyncio.sleep(self.retry_timeout)
                _LOGGER.warning("Failed to download, retrying... (Attempt %d of %d)", retry_count + 1, max_retries)
        return None  # pragma: no cover

    async def download_profile(self, manufacturer: str, model: str, storage_path: str, model_hash: str) -> None:
        """
        Download the profile from Github using the Powercalc download API
        Saves the profile to manufacturer/model directory in .storage/powercalc_profiles folder
        """

        _LOGGER.debug("Downloading profile: %s/%s from github", manufacturer, model)

        endpoint = f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}"

        session = async_get_clientsession(self.hass)

        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                async with session.get(endpoint, params={"hash": model_hash}) as resp:
                    if resp.status != 200:
                        raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}")
                    resources = await resp.json()

                validated_resources = await self.hass.async_add_executor_job(
                    _validate_resources,
                    resources,
                    storage_path,
                )

                await self.hass.async_add_executor_job(lambda: os.makedirs(storage_path, exist_ok=True))

                # Download the files
                downloaded_resources: list[tuple[bytes, Path]] = []
                for url, destination in validated_resources:
                    async with session.get(url, allow_redirects=False) as resp:
                        if resp.status != 200:
                            raise ProfileDownloadError(f"Failed to download github URL: {url}")

                        contents = await resp.read()
                        downloaded_resources.append((contents, destination))

                await self.hass.async_add_executor_job(_save_resources, downloaded_resources)
        except (TimeoutError, aiohttp.ClientError) as e:
            raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}") from e

    def _get_profile_hashes_path(self) -> str:
        """Retrieve the local storage path for the profile hashes file."""
        return str(self.hass.config.path(STORAGE_DIR, BUILT_IN_LIBRARY_DIR, ".profile_hashes"))

    def _load_profile_hashes(self) -> dict[str, str]:
        """Load profile hashes from local storage.

        An unusable file is treated as empty rather than raised: the hashes are only a cache
        validity marker, so the worst case is that every profile is downloaded once more.
        """

        path = self._get_profile_hashes_path()
        if not os.path.exists(path):
            return {}

        try:
            with open(path) as f:
                return cast(dict[str, str], json.load(f))
        except (JSONDecodeError, OSError) as err:
            _LOGGER.warning("Profile hashes file is unusable (%s), profiles will be downloaded again", err)
            return {}

    def _write_profile_hashes(self, hashes: dict[str, str]) -> None:
        """Write profile hashes to local storage, atomically."""

        path = self._get_profile_hashes_path()
        _save_resource(json.dumps(hashes, indent=4).encode(), Path(path))
