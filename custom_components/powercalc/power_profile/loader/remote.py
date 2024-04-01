import json
import logging
import os

import aiohttp
from githubkit import GitHub, TokenAuthStrategy
from githubkit.versions.v2022_11_28.models import ContentDirectoryItems
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.powercalc.helpers import get_library_path
from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

REPO_OWNER = "bramstroker"
REPO_NAME = "homeassistant-powercalc"

_LOGGER = logging.getLogger(__name__)


class RemoteLoader(Loader):
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.library_contents: dict = {}
        self.model_infos: dict[str, dict] = {}
        self.manufacturer_models: dict[str, list[dict]] = {}

    async def initialize(self) -> None:
        # Todo: async io
        with open(get_library_path("library.json")) as f:
            self.library_contents = json.load(f)

        if not self.library_contents:
            raise LibraryLoadingError("Library.json JSON invalid")

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

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""

        return {
            m["name"] for m
            in self.library_contents.get("manufacturers", [])
            if device_type in m.get("device_types", [])
        }

    async def get_model_listing(self, manufacturer: str) -> set[str]:
        """Get listing of available models for a given manufacturer."""

        return {model["id"] for model in self.manufacturer_models.get(manufacturer, [])}

    async def load_model(self, manufacturer: str, model: str, directory: str | None) -> tuple[dict, str] | None:

        # This loader does not support loading from local directory
        if directory is not None:
            return None

        model_info = self.model_infos.get(f"{manufacturer}/{model}")
        if not model_info:
            raise FileNotFoundError("Model not found in library: %s/%s", manufacturer, model)

        storage_path = self.hass.config.path(STORAGE_DIR, "powercalc_profiles", manufacturer, model)

        needs_update = False
        path_exists = os.path.exists(storage_path)
        if not path_exists:
            needs_update = True

        # if path_exists:
        #     remote_modification_time = model_info.get("last_update", time.time())
        #     local_modification_time = self._get_local_modification_time(storage_path)
        #     if remote_modification_time > local_modification_time:
        #         _LOGGER.debug("Remote profile is newer than local profile")
        #         needs_update = True

        if needs_update:
            await self._download_profile(manufacturer, model, storage_path)

        model_path = os.path.join(storage_path, "model.json")

        with open(model_path) as f:
            json_data = json.load(f)

        return json_data, storage_path

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

    async def _download_profile(self, manufacturer: str, model: str, storage_path: str) -> None:
        """Download the profile from github."""
        folder = "custom_components/powercalc/data/signify/LCT010"

        github = GitHub(TokenAuthStrategy("<access_token>"))

        _LOGGER.info("Downloading profile: %s/%s from github", manufacturer, model)

        content_response = await github.rest.repos.async_get_content(
            owner=REPO_OWNER,
            repo=REPO_NAME,
            path=folder,
        )

        if content_response.status_code != 200:
            raise ProfileDownloadError(f"Failed to download profile: {manufacturer}/{model}")

        os.makedirs(storage_path, exist_ok=True)

        # Download the files
        async with aiohttp.ClientSession() as session:
            for file in content_response.parsed_data:
                if not isinstance(file, ContentDirectoryItems) or not file.download_url:
                    continue
                async with session.get(file.download_url) as resp:
                    with open(os.path.join(storage_path, file.name), "wb") as f:
                        f.write(await resp.read())

