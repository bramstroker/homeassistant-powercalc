from collections.abc import Iterator
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.loader.profile_cache import install_profile
from custom_components.powercalc.power_profile.loader.remote import ENDPOINT_DOWNLOAD, ENDPOINT_LIBRARY, RemoteLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType, DiscoveryBy

pytestmark = pytest.mark.skip_remote_loader_mocking

RESOURCE_URL = "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/test/model"
OLD_MODEL = {
    "id": "model",
    "name": "Original model",
    "aliases": ["original-alias"],
    "device_type": "fan",
    "discovery_by": "entity",
    "hash": "old",
    "min_version": "1.0.0",
}
NEW_MODEL = {
    **OLD_MODEL,
    "name": "Updated model",
    "aliases": ["new-alias"],
    "device_type": "light",
    "hash": "new",
    "min_version": "2.0.0",
}
OLD_PROFILE = {
    "name": "Original model",
    "aliases": ["original-alias"],
    "device_type": "fan",
    "min_version": "1.0.0",
    "calculation_strategy": "fixed",
    "fixed_config": {"power": 3},
}
NEW_PROFILE = {"min_version": "2.0.0", "calculation_strategy": "lut"}


@pytest.fixture
def integration_version(hass: HomeAssistant, tmp_path: Path) -> Iterator[SimpleNamespace]:
    hass.config.config_dir = str(tmp_path)
    integration = SimpleNamespace(version="1.0.0")
    with patch(
        "custom_components.powercalc.power_profile.loader.remote.async_get_integration",
        new=AsyncMock(return_value=integration),
    ):
        yield integration


def mock_library(response: aioresponses, model: dict) -> None:
    response.get(
        ENDPOINT_LIBRARY,
        payload={"manufacturers": [{"dir_name": "test", "full_name": "Test", "models": [model]}]},
    )


def mock_profile(
    response: aioresponses, model_hash: str, profile: dict, extra_files: dict[str, bytes] | None = None
) -> None:
    files = {"model.json": json.dumps(profile).encode(), **(extra_files or {})}
    response.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash={model_hash}",
        payload=[{"path": name, "url": f"{RESOURCE_URL}/{name}"} for name in files],
        repeat=True,
    )
    for name, data in files.items():
        response.get(f"{RESOURCE_URL}/{name}", body=data, repeat=True)


async def test_installed_profile_survives_update_restart_and_force_then_upgrades(
    hass: HomeAssistant,
    integration_version: SimpleNamespace,
) -> None:
    loader = RemoteLoader(hass)
    library = ProfileLibrary(hass, loader)
    with aioresponses() as response:
        mock_library(response, OLD_MODEL)
        mock_profile(response, "old", OLD_PROFILE, {"obsolete.csv": b"old data"})
        await library.initialize()
        profile = await library.get_profile(ModelInfo("test", "original-alias"))
        assert profile.fixed_config == {"power": 3}

    with aioresponses() as response:
        mock_library(response, NEW_MODEL)
        await library.initialize()
        assert (await library.get_profile(ModelInfo("test", "model"))).fixed_config == {"power": 3}
        assert await loader.find_model("test", {"original-alias"}) == ["model"]
        assert await loader.find_model("test", {"new-alias"}) == []
        assert await loader.get_manufacturer_listing({DeviceType.FAN}) == {("test", "Test")}
        assert await loader.get_model_listing("test", {DeviceType.FAN}) == {("model", "Original model")}
        metadata = await loader.get_model_metadata("test", "model")
        assert metadata.device_type == DeviceType.FAN
        assert metadata.discovery_by == DiscoveryBy.ENTITY
        data, directory = await loader.load_model("test", "model", force_update=True)
        assert data == OLD_PROFILE
        # No profile endpoint is registered, and even a failed attempt would be recorded.
        assert all(str(url) == ENDPOINT_LIBRARY for _, url in response.requests)

    # A fresh loader has only the updated index and the independently persisted installed revision.
    with aioresponses() as response:
        restarted = RemoteLoader(hass)
        await restarted.initialize(prefer_cached=True)
        assert (await restarted.load_model("test", "model", force_update=True))[0] == OLD_PROFILE
        assert not response.requests

    integration_version.version = "2.0.0"
    with aioresponses() as response:
        mock_library(response, NEW_MODEL)
        mock_profile(response, "new", NEW_PROFILE, {"hs.csv": b"bri,hue,sat,watt\n255,0,255,5\n"})
        await restarted.initialize()
        data, updated_directory = await restarted.load_model("test", "model")
        assert data == NEW_PROFILE
        assert directory == updated_directory
        assert not await hass.async_add_executor_job((Path(directory) / "obsolete.csv").exists)
        assert await hass.async_add_executor_job((Path(directory) / "hs.csv").is_file)

    # Installed metadata is sufficient even if the old hash cache was lost before shutdown.
    await hass.async_add_executor_job(Path(restarted._get_profile_hashes_path()).unlink)  # noqa: SLF001
    with aioresponses() as response:
        restarted = RemoteLoader(hass)
        await restarted.initialize(prefer_cached=True)
        assert (await restarted.load_model("test", "model"))[0] == NEW_PROFILE
        assert not response.requests


@pytest.mark.usefixtures("integration_version")
async def test_legacy_cache_uses_its_own_metadata(hass: HomeAssistant) -> None:
    loader = RemoteLoader(hass)
    storage = Path(loader.get_storage_path("test", "model"))

    def write_legacy() -> None:
        storage.mkdir(parents=True)
        (storage / "model.json").write_text(json.dumps(OLD_PROFILE))
        (storage / ".powercalc").mkdir()
        loader._write_profile_hashes({"test/model": "old"})  # noqa: SLF001

    await hass.async_add_executor_job(write_legacy)
    with aioresponses() as response:
        mock_library(response, NEW_MODEL)
        await loader.initialize()
        assert await loader.find_model("test", {"original-alias"}) == ["model"]
        assert (await loader.load_model("test", "model", force_update=True))[0] == OLD_PROFILE
        restarted = RemoteLoader(hass)
        await restarted.initialize(prefer_cached=True)
        assert (await restarted.load_model("test", "model"))[0] == OLD_PROFILE
        library = ProfileLibrary(hass, restarted)
        profile = await library.get_profile(ModelInfo("test", "model"))
        assert not await profile.has_sub_profiles
        assert all(str(url) == ENDPOINT_LIBRARY for _, url in response.requests)


@pytest.mark.usefixtures("integration_version")
async def test_incompatible_profile_without_cache_is_not_loadable(hass: HomeAssistant) -> None:
    loader = RemoteLoader(hass)
    with aioresponses() as response:
        mock_library(response, NEW_MODEL)
        await loader.initialize()
        assert await loader.find_model("test", {"model"}) == []
        with pytest.raises(LibraryLoadingError, match="requires Powercalc"):
            await loader.load_model("test", "model", force_update=True)
        assert all(str(url) == ENDPOINT_LIBRARY for _, url in response.requests)


async def test_downgrade_rejects_installed_newer_profile(
    hass: HomeAssistant,
    integration_version: SimpleNamespace,
) -> None:
    integration_version.version = "2.0.0"
    with aioresponses() as response:
        mock_library(response, NEW_MODEL)
        mock_profile(response, "new", NEW_PROFILE)
        loader = RemoteLoader(hass)
        await loader.initialize()
        await loader.load_model("test", "model")

    integration_version.version = "1.0.0"
    with aioresponses() as response:
        loader = RemoteLoader(hass)
        await loader.initialize(prefer_cached=True)
        assert await loader.get_model_listing("test", None) == set()
        with pytest.raises(LibraryLoadingError, match="requires Powercalc"):
            await loader.load_model("test", "model")
        assert not response.requests


@pytest.mark.usefixtures("integration_version")
async def test_fallback_does_not_download_if_cached_files_disappear(hass: HomeAssistant) -> None:
    with aioresponses() as response:
        mock_library(response, OLD_MODEL)
        mock_profile(response, "old", OLD_PROFILE)
        loader = RemoteLoader(hass)
        await loader.initialize()
        _, directory = await loader.load_model("test", "model")

    with aioresponses() as response:
        mock_library(response, NEW_MODEL)
        await loader.initialize()
        await hass.async_add_executor_job((Path(directory) / "model.json").unlink)
        with pytest.raises(LibraryLoadingError, match="No compatible installed profile"):
            await loader.load_model("test", "model", force_update=True)
        assert all(str(url) == ENDPOINT_LIBRARY for _, url in response.requests)


@pytest.mark.parametrize("failure", ["incompatible", "invalid_json", "missing_model", "write_error"])
@pytest.mark.usefixtures("integration_version")
async def test_failed_update_preserves_files_and_metadata(hass: HomeAssistant, failure: str) -> None:
    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    with aioresponses() as response:
        mock_library(response, OLD_MODEL)
        mock_profile(response, "old", OLD_PROFILE, {"hs.csv": b"old data"})
        await loader.initialize()
        _, directory = await loader.load_model("test", "model")
    original_metadata = await hass.async_add_executor_job((Path(directory) / ".installed.json").read_bytes)

    with aioresponses() as response:
        mock_library(response, {**OLD_MODEL, "hash": "new"})
        await loader.initialize()
        # The index may lag behind a profile download, so check the downloaded JSON as well.
        if failure == "incompatible":
            mock_profile(response, "new", NEW_PROFILE, {"hs.csv": b"new data"})
        elif failure == "invalid_json":
            mock_profile(response, "new", OLD_PROFILE, {"model.json": b"{", "hs.csv": b"new data"})
        elif failure == "missing_model":
            response.get(f"{ENDPOINT_DOWNLOAD}/test/model?hash=new", payload=[], repeat=True)
        else:
            mock_profile(response, "new", OLD_PROFILE, {"hs.csv": b"new data"})

        with patch(
            "custom_components.powercalc.power_profile.loader.remote.install_profile",
            side_effect=OSError("disk full") if failure == "write_error" else install_profile,
        ):
            assert (await loader.load_model("test", "model", force_update=True))[0] == OLD_PROFILE

    assert await hass.async_add_executor_job((Path(directory) / "hs.csv").read_bytes) == b"old data"
    assert await hass.async_add_executor_job((Path(directory) / ".installed.json").read_bytes) == original_metadata
    with aioresponses() as response:
        # Subsequent incompatible library updates must still find the original installed metadata.
        mock_library(response, NEW_MODEL)
        restarted = RemoteLoader(hass)
        await restarted.initialize()
        assert (await restarted.load_model("test", "model"))[0] == OLD_PROFILE


@pytest.mark.parametrize("has_cached_profile", [False, True])
@pytest.mark.parametrize("error", [OSError("disk full"), PermissionError("read-only cache")])
@pytest.mark.usefixtures("integration_version")
async def test_staging_failure_uses_cached_profile_or_raises_download_error(
    hass: HomeAssistant, has_cached_profile: bool, error: OSError
) -> None:
    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    with aioresponses() as response:
        mock_library(response, OLD_MODEL)
        mock_profile(response, "old", OLD_PROFILE)
        await loader.initialize()
        if has_cached_profile:
            _, directory = await loader.load_model("test", "model")
            metadata_path = Path(directory) / ".installed.json"
            original_metadata = await hass.async_add_executor_job(metadata_path.read_bytes)

    with (
        patch(
            "custom_components.powercalc.power_profile.loader.remote.create_staging_directory",
            side_effect=error,
        ) as create_staging,
        patch.object(loader, "download_profile") as download,
    ):
        if has_cached_profile:
            assert (await loader.load_model("test", "model", force_update=True))[0] == OLD_PROFILE
            assert await hass.async_add_executor_job(metadata_path.read_bytes) == original_metadata
        else:
            with pytest.raises(ProfileDownloadError):
                await loader.load_model("test", "model", force_update=True)
        assert create_staging.call_count == 3
        download.assert_not_called()


@pytest.mark.usefixtures("integration_version")
async def test_incompatible_download_is_rejected_on_fresh_install(hass: HomeAssistant) -> None:
    with aioresponses() as response:
        mock_library(response, OLD_MODEL)
        mock_profile(response, "old", NEW_PROFILE)
        loader = RemoteLoader(hass)
        loader.retry_timeout = 0
        await loader.initialize()
        with pytest.raises(ProfileDownloadError):
            await loader.load_model("test", "model")
