import contextlib
from functools import partial
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientError
from aioresponses import aioresponses
from awesomeversion import AwesomeVersion
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR
import pytest

from custom_components.powercalc.const import LIBRARY_DISCOVERY_LOW_PRIORITY_DOMAINS
from custom_components.powercalc.helpers import get_library_json_path, get_library_path
from custom_components.powercalc.power_profile.error import LibraryLoadingError, ProfileDownloadError
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.loader.remote import (
    ENDPOINT_DOWNLOAD,
    ENDPOINT_LIBRARY,
    LibraryModel,
    RemoteLoader,
)
from custom_components.powercalc.power_profile.power_profile import DeviceType, DiscoveryBy
from tests.common import get_test_config_dir, get_test_profile_dir

pytestmark = pytest.mark.skip_remote_loader_mocking


@pytest.fixture
def mock_aioresponse() -> aioresponses:
    with aioresponses() as m:
        yield m


@pytest.fixture
def mock_library_json_response(mock_aioresponse: aioresponses) -> None:
    local_library_path = get_library_json_path()
    with open(local_library_path) as f:
        library_json = json.load(f)

    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload=library_json,
    )


@pytest.fixture
async def remote_loader(hass: HomeAssistant, mock_library_json_response: None) -> RemoteLoader:
    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize()
    return loader


@pytest.fixture
def mock_download_profile_endpoints(mock_aioresponse: aioresponses) -> list[dict]:
    remote_files = [
        {
            "path": "color_temp.csv.gz",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/color_temp.csv.gz",
        },
        {
            "path": "hs.csv.gz",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/hs.csv.gz",
        },
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/model.json",
        },
    ]

    mock_aioresponse.get(
        re.compile(rf"{ENDPOINT_DOWNLOAD}/signify/LCA001.*"),
        status=200,
        payload=remote_files,
        repeat=True,
    )

    for remote_file in remote_files:
        with open(get_test_profile_dir("signify_LCA001") + f"/{remote_file['path']}", "rb") as f:
            mock_aioresponse.get(
                remote_file["url"],
                status=200,
                body=f.read(),
                repeat=True,
            )
    return remote_files


async def test_download(
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
    mock_download_profile_endpoints: list[dict],
) -> None:
    """Mock the API response for the download of a profile."""
    remote_files = mock_download_profile_endpoints

    storage_dir = get_test_profile_dir("download")
    await remote_loader.download_profile("signify", "LCA001", storage_dir, "test_download")

    for remote_file in remote_files:
        assert await remote_loader.hass.async_add_executor_job(
            os.path.exists,
            os.path.join(storage_dir, remote_file["path"]),
        )


async def test_download_with_parenthesis(remote_loader: RemoteLoader, mock_aioresponse: aioresponses) -> None:
    remote_files = [
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/google/Home Mini (HOA)/model.json",  # noqa: E501
        },
    ]

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/google/Home Mini (HOA)?hash=test_download",
        status=200,
        payload=remote_files,
        repeat=True,
    )

    for remote_file in remote_files:
        with open(get_library_path("google/Home Mini (HOA)") + f"/{remote_file['path']}", "rb") as f:
            mock_aioresponse.get(
                remote_file["url"],
                status=200,
                body=f.read(),
                repeat=True,
            )

    storage_dir = get_test_profile_dir("download")
    await remote_loader.download_profile("google", "Home Mini (HOA)", storage_dir, "test_download")

    for remote_file in remote_files:
        assert await remote_loader.hass.async_add_executor_job(
            os.path.exists,
            os.path.join(storage_dir, remote_file["path"]),
        )


@pytest.mark.parametrize(
    "resource_url",
    [
        "http://raw.githubusercontent.com/example/profile/model.json",
        "https://example.com/profile/model.json",
        "https://raw.githubusercontent.com.example.com/profile/model.json",
        "https://github.com@127.0.0.1/profile/model.json",
        "https://github.com:444/profile/model.json",
        "https://github.com:invalid/profile/model.json",
        None,
    ],
)
async def test_download_rejects_untrusted_resource_url(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    tmp_path: Path,
    resource_url: str | None,
) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=[{"path": "model.json", "url": resource_url}],
    )

    with pytest.raises(ProfileDownloadError, match="URL"):
        await remote_loader.download_profile("test", "model", str(tmp_path / "profiles"), "test_download")


@pytest.mark.parametrize("resource_path", ["../outside.json", "nested/../../outside.json", "", None])
async def test_download_rejects_invalid_resource_path(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    tmp_path: Path,
    resource_path: str | None,
) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=[
            {
                "path": resource_path,
                "url": "https://raw.githubusercontent.com/example/profile/model.json",
            },
        ],
    )

    with pytest.raises(ProfileDownloadError, match="path"):
        await remote_loader.download_profile("test", "model", str(tmp_path / "profiles"), "test_download")


async def test_download_rejects_invalid_storage_path(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=[
            {
                "path": "model.json",
                "url": "https://raw.githubusercontent.com/example/profile/model.json",
            },
        ],
    )

    with pytest.raises(ProfileDownloadError, match="invalid path"):
        await remote_loader.download_profile("test", "model", "invalid\0path", "test_download")


@pytest.mark.parametrize("resources", [{}, ["invalid"]])
async def test_download_rejects_invalid_resource_manifest(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    tmp_path: Path,
    resources: object,
) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=resources,
    )

    with pytest.raises(ProfileDownloadError, match="invalid resources"):
        await remote_loader.download_profile("test", "model", str(tmp_path / "profiles"), "test_download")


async def test_download_rejects_absolute_resource_path(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    tmp_path: Path,
) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=[
            {
                "path": str(tmp_path / "outside.json"),
                "url": "https://raw.githubusercontent.com/example/profile/model.json",
            },
        ],
    )

    with pytest.raises(ProfileDownloadError, match="path"):
        await remote_loader.download_profile("test", "model", str(tmp_path / "profiles"), "test_download")

    assert not (tmp_path / "outside.json").exists()


async def test_download_rejects_resource_path_through_symlink(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "profiles"
    outside_path = tmp_path / "outside"
    storage_path.mkdir()
    outside_path.mkdir()
    (storage_path / "linked").symlink_to(outside_path, target_is_directory=True)
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=[
            {
                "path": "linked/model.json",
                "url": "https://raw.githubusercontent.com/example/profile/model.json",
            },
        ],
    )

    with pytest.raises(ProfileDownloadError, match="path"):
        await remote_loader.download_profile("test", "model", str(storage_path), "test_download")

    assert not (outside_path / "model.json").exists()


async def test_download_does_not_follow_resource_redirects(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    tmp_path: Path,
) -> None:
    resource_url = "https://raw.githubusercontent.com/example/profile/model.json"
    redirected_url = "http://192.168.1.1/model.json"
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/test/model?hash=test_download",
        status=200,
        payload=[{"path": "model.json", "url": resource_url}],
    )
    mock_aioresponse.get(resource_url, status=302, headers={"Location": redirected_url})
    mock_aioresponse.get(redirected_url, status=200, body=b"untrusted")
    storage_path = tmp_path / "profiles"

    with pytest.raises(ProfileDownloadError, match="Failed to download github URL"):
        await remote_loader.download_profile("test", "model", str(storage_path), "test_download")

    assert not (storage_path / "model.json").exists()


async def test_get_manufacturer_listing(remote_loader: RemoteLoader) -> None:
    manufacturers = await remote_loader.get_manufacturer_listing({DeviceType.LIGHT})
    assert ("signify", "Signify") in manufacturers
    assert len(manufacturers) > 40
    assert ("signify", "Signify") in await remote_loader.get_manufacturer_listing(None, DiscoveryBy.DEVICE)


async def test_get_discovery_low_priority_domains(remote_loader: RemoteLoader) -> None:
    remote_loader.library_contents[LIBRARY_DISCOVERY_LOW_PRIORITY_DOMAINS] = ["low_priority", "other"]

    assert remote_loader.get_discovery_low_priority_domains() == {"low_priority", "other"}


async def test_get_model_listing(remote_loader: RemoteLoader) -> None:
    models = await remote_loader.get_model_listing("signify", {DeviceType.LIGHT})
    assert ("LCT010", "Hue White and Color Ambiance A19 E26 (Gen 3)") in models
    assert len(models) > 40
    device_models = await remote_loader.get_model_listing("signify", None, DiscoveryBy.DEVICE)
    assert ("BSB002", "Hue Bridge V2") in device_models
    assert ("LCT010", "Hue White and Color Ambiance A19 E26 (Gen 3)") not in device_models


async def test_get_model_metadata_rejects_invalid_device_type(remote_loader: RemoteLoader) -> None:
    remote_loader.model_infos["test/invalid"] = cast(
        "LibraryModel",
        {"id": "invalid", "hash": "hash", "device_type": "invalid"},
    )

    assert await remote_loader.get_model_metadata("test", "invalid") is None


async def test_get_model_metadata_rejects_invalid_discovery_by(remote_loader: RemoteLoader) -> None:
    remote_loader.model_infos["test/invalid"] = cast(
        "LibraryModel",
        {"id": "invalid", "hash": "hash", "device_type": "light", "discovery_by": "invalid"},
    )

    assert await remote_loader.get_model_metadata("test", "invalid") is None


async def test_listings_skip_models_with_unknown_values(hass: HomeAssistant, mock_aioresponse: aioresponses) -> None:
    """Models using a device type or discovery mode introduced in a newer Powercalc version must be ignored.

    They may never break the listings for the installed version.
    """
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload={
            "manufacturers": [
                {
                    "name": "future",
                    "full_name": "Future",
                    "dir_name": "future",
                    "models": [
                        {"id": "unknown_device_type", "device_type": "spaceship", "hash": "dummy"},
                        {
                            "id": "unknown_discovery_by",
                            "device_type": "light",
                            "discovery_by": "galaxy",
                            "hash": "dummy",
                        },
                    ],
                },
                {
                    "name": "known",
                    "full_name": "Known",
                    "dir_name": "known",
                    "models": [{"id": "some_light", "device_type": "light", "hash": "dummy"}],
                },
            ],
        },
    )

    loader = RemoteLoader(hass)
    await loader.initialize()

    for device_types in (None, {DeviceType.LIGHT}):
        manufacturers = await loader.get_manufacturer_listing(device_types, DiscoveryBy.ENTITY)
        assert ("known", "Known") in manufacturers
        assert ("future", "Future") not in manufacturers

    assert await loader.get_model_listing("future", None) == set()
    assert await loader.get_model_metadata("future", "unknown_discovery_by") is None


async def test_manufacturer_listing_skips_models_requiring_newer_version(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
) -> None:
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload={
            "manufacturers": [
                {
                    "name": "test_manu",
                    "full_name": "Test manufacturer",
                    "dir_name": "test_manu",
                    "models": [
                        {"id": "future_profile", "device_type": "light", "hash": "dummy", "min_version": "v99.0.0"},
                    ],
                },
            ],
        },
    )

    loader = RemoteLoader(hass)
    await loader.initialize()

    assert await loader.get_manufacturer_listing(None) == set()


async def test_find_model_migration(hass: HomeAssistant, mock_aioresponse: aioresponses) -> None:
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload={
            "manufacturers": [
                {
                    "name": "eglo",
                    "dir_name": "eglo",
                    "aliases": ["EGLO Leuchten"],
                    "models": [
                        {
                            "id": "900053",
                            "device_type": "light",
                            "legacy_ids": ["33955"],
                            "updated_at": "2026-03-25T15:08:09Z",
                            "hash": "dummy",
                        },
                    ],
                },
            ],
        },
    )

    library = await ProfileLibrary.factory(hass)

    assert await library.find_model_migration(ModelInfo("eglo", "33955")) == ModelInfo("eglo", "900053", None)
    assert await library.find_model_migration(ModelInfo("EGLO Leuchten".lower(), "33955")) == ModelInfo(
        "eglo",
        "900053",
        None,
    )


async def test_load_model_raises_library_exception_on_non_existing_model(remote_loader: RemoteLoader) -> None:
    with pytest.raises(LibraryLoadingError):
        await remote_loader.load_model("signify", "NON_EXISTING_MODEL")


async def test_download_profile_exception_unexpected_status_code(
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
) -> None:
    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/signify/LCA001?hash=test_download",
        status=500,
        repeat=True,
    )

    profile_dir = get_test_profile_dir("download")
    with pytest.raises(ProfileDownloadError):
        await remote_loader.download_profile("signify", "LCA001", profile_dir, "test_download")


async def test_exception_is_raised_on_connection_error(
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
) -> None:
    mock_aioresponse.get(f"{ENDPOINT_DOWNLOAD}/signify/LCA001?hash=test_download", exception=ClientError("test"))

    profile_dir = get_test_profile_dir("download")
    with pytest.raises(ProfileDownloadError):
        await remote_loader.download_profile("signify", "LCA001", profile_dir, "test_download")


async def test_exception_is_raised_on_github_resource_unavailable(
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
) -> None:
    manufacturer = "signify"
    model = "LCA001"
    storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(storage_path)

    remote_file = {
        "path": "color_temp.csv.gz",
        "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/color_temp.csv.gz",
    }

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}?hash=6288837291e73d208e2d408b6b66c8f0",
        status=200,
        payload=[remote_file],
        repeat=True,
    )

    mock_aioresponse.get(
        remote_file["url"],
        status=500,
        repeat=True,
    )

    remote_loader.retry_timeout = 0
    with pytest.raises(ProfileDownloadError):
        await remote_loader.load_model(manufacturer, model)


async def test_eventual_success_after_download_retry(
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
) -> None:
    manufacturer = "signify"
    model = "LCA001"
    storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(storage_path)

    remote_file = {
        "path": "color_temp.csv.gz",
        "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/signify/LCA001/color_temp.csv.gz",
    }

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}?hash=test_download",
        status=200,
        payload=[remote_file],
        repeat=True,
    )

    mock_aioresponse.get(remote_file["url"], status=500)
    mock_aioresponse.get(remote_file["url"], status=200)

    callback = partial(remote_loader.download_profile, manufacturer, model, storage_path, "test_download")
    await remote_loader.download_with_retry(callback)

    assert await remote_loader.hass.async_add_executor_job(os.path.exists, storage_path)


@pytest.mark.parametrize(
    "profile_hash,local_hash,exists_locally,expected_download",
    [
        ("018de85593a1b22b906f863677bb4891", None, True, True),
        ("018de85593a1b22b906f863677bb4891", "b3e12b2e89ca7db698abeb39e2d7d2d3", True, True),
        ("018de85593a1b22b906f863677bb4891", "018de85593a1b22b906f863677bb4891", True, False),
        ("018de85593a1b22b906f863677bb4891", "018de85593a1b22b906f863677bb4891", False, True),
    ],
)
@pytest.mark.usefixtures("mock_download_profile_endpoints")
async def test_profile_redownloaded_when_newer_version_available(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    profile_hash: str | None,
    local_hash: str | None,
    exists_locally: bool,
    expected_download: bool,
) -> None:
    def _count_download_requests() -> int:
        for req, calls in mock_aioresponse.requests.items():
            if str(req[1]).startswith(ENDPOINT_DOWNLOAD):
                return len(calls)
        return 0

    def _mock_library_json() -> None:
        mock_aioresponse.get(
            ENDPOINT_LIBRARY,
            status=200,
            payload={
                "manufacturers": [
                    {
                        "name": "signify",
                        "dir_name": "signify",
                        "models": [
                            {
                                "id": "LCA001",
                                "device_type": "light",
                                "hash": profile_hash,
                            },
                        ],
                    },
                ],
            },
            repeat=True,
        )

    _mock_library_json()

    loader = RemoteLoader(hass)

    # Clean local directory first so we have consistent test results
    # When scenario exists_locally=True, we download the profile first, to fake the local existence
    local_storage_path = loader.get_storage_path("signify", "LCA001")
    clear_storage_dir(local_storage_path)
    hash_file = hass.config.path(STORAGE_DIR, "powercalc_profiles", ".profile_hashes")
    if await hass.async_add_executor_job(os.path.exists, hash_file):
        await hass.async_add_executor_job(os.remove, hash_file)

    if local_hash:
        loader._write_profile_hashes({"signify/LCA001": local_hash})  # noqa: SLF001

    await loader.initialize()

    if exists_locally:
        await loader.download_profile("signify", "LCA001", local_storage_path, profile_hash)

    await loader.load_model("signify", "LCA001")

    actual_call_count = _count_download_requests()
    if exists_locally:
        actual_call_count -= 1

    expected_call_count = 1 if expected_download else 0
    assert actual_call_count == expected_call_count


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 404}, id="not found"),
        # See: https://github.com/bramstroker/homeassistant-powercalc/issues/2277
        pytest.param({"status": 200, "exception": ClientError("test")}, id="connection error"),
        pytest.param({"status": 200, "exception": TimeoutError("test")}, id="timeout"),
    ],
)
async def test_fallback_to_local_library(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    caplog: pytest.LogCaptureFixture,
    response_kwargs: dict,
) -> None:
    """
    Test that the local library is used when the remote library is not available.
    When unavailable, it should retry 3 times before falling back to the local library.
    """
    shutil.copy(get_library_json_path(), hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    caplog.set_level(logging.WARNING)
    mock_aioresponse.get(ENDPOINT_LIBRARY, repeat=True, **response_kwargs)

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize()

    assert "signify" in loader.model_lookup
    assert len(caplog.records) >= 2


async def test_fallback_to_local_library_fails(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After 3 retries with no prior library.json in .storage, it should raise ProfileDownloadError."""

    with contextlib.suppress(FileNotFoundError):
        os.remove(hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    caplog.set_level(logging.WARNING)
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=404,
        repeat=True,
    )

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    with pytest.raises(ProfileDownloadError):
        await loader.initialize()


async def test_prefer_cached_skips_download(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
) -> None:
    """With a library.json in local storage, initialize must not touch the download API."""
    shutil.copy(get_library_json_path(), hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    # Any request to the library endpoint fails the test, nothing may be downloaded.
    mock_aioresponse.get(ENDPOINT_LIBRARY, repeat=True, exception=AssertionError("library.json was downloaded"))

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize(prefer_cached=True)

    assert "signify" in loader.model_lookup


async def test_prefer_cached_downloads_when_no_local_copy(
    hass: HomeAssistant,
    mock_library_json_response: None,
) -> None:
    """On a fresh install there is nothing cached yet, so it must still download."""
    with contextlib.suppress(FileNotFoundError):
        os.remove(hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize(prefer_cached=True)

    assert "signify" in loader.model_lookup


async def test_library_update_refreshes_from_remote(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
) -> None:
    """The periodic update must re-download, even though a local copy exists."""
    shutil.copy(get_library_json_path(), hass.config.path(STORAGE_DIR, "powercalc_profiles", "library.json"))

    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload={
            "manufacturers": [
                {
                    "name": "acme",
                    "dir_name": "acme",
                    "models": [{"id": "widget", "device_type": "light", "hash": "dummy"}],
                },
            ],
        },
    )

    loader = RemoteLoader(hass)
    loader.retry_timeout = 0
    await loader.initialize()

    assert "acme" in loader.model_lookup
    assert "signify" not in loader.model_lookup


async def test_fallback_to_local_profile(
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
) -> None:
    manufacturer = "signify"
    model = "LCA001"
    local_storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(local_storage_path)
    shutil.copytree(get_library_path(f"{manufacturer}/{model}"), local_storage_path)

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}",
        status=500,
        repeat=True,
    )

    assert await remote_loader.load_model(manufacturer, model, force_update=True)


async def test_fallback_to_local_profile_on_timeout(
    hass: HomeAssistant,
    mock_aioresponse: aioresponses,
    remote_loader: RemoteLoader,
) -> None:
    manufacturer = "signify"
    model = "LCA001"
    local_storage_path = remote_loader.get_storage_path(manufacturer, model)
    clear_storage_dir(local_storage_path)
    shutil.copytree(get_library_path(f"{manufacturer}/{model}"), local_storage_path)

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/{manufacturer}/{model}",
        status=200,
        repeat=True,
        exception=TimeoutError("test"),
    )

    assert await remote_loader.load_model(manufacturer, model, force_update=True)


@pytest.mark.usefixtures("mock_download_profile_endpoints")
async def test_profile_redownloaded_when_model_json_missing(
    hass: HomeAssistant,
    remote_loader: RemoteLoader,
) -> None:
    """Test profile is redownloaded when model.json is missing."""
    local_storage_path = remote_loader.get_storage_path("signify", "LCA001")
    shutil.rmtree(local_storage_path, ignore_errors=True)
    os.makedirs(local_storage_path)

    (__, storage_path) = await remote_loader.load_model("signify", "LCA001")
    assert storage_path == local_storage_path


async def test_profile_redownloaded_when_model_json_corrupt(
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Corrupt the model.json file and check if it is redownloaded."""
    local_storage_path = remote_loader.get_storage_path("apple", "HomePod Mini")
    shutil.rmtree(local_storage_path, ignore_errors=True)
    os.makedirs(local_storage_path)

    remote_files = [
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/apple/HomePod Mini/model.json",  # noqa: E501
        },
    ]

    mock_aioresponse.get(
        re.compile(rf"{ENDPOINT_DOWNLOAD}/apple/HomePod.*"),
        status=200,
        payload=remote_files,
        repeat=True,
    )

    mock_aioresponse.get(
        remote_files[0]["url"],
        status=200,
        body="invalid json",
    )
    with open(get_library_path("apple/HomePod Mini/model.json"), "rb") as f:
        mock_aioresponse.get(
            remote_files[0]["url"],
            status=200,
            body=f.read(),
        )

    await remote_loader.load_model("apple", "HomePod Mini")

    assert "model.json file is not valid JSON" in caplog.text
    assert "Retrying to load model.json file" in caplog.text


async def test_profile_redownloaded_when_model_json_corrupt_retry_limit(
    hass: HomeAssistant,
    remote_loader: RemoteLoader,
    mock_aioresponse: aioresponses,
) -> None:
    """
    When model.json is corrupt, retry 3 times before giving up.
    After 3 times it should raise a LibraryLoadingError.
    """
    local_storage_path = remote_loader.get_storage_path("apple", "HomePod Mini")
    shutil.rmtree(local_storage_path, ignore_errors=True)
    os.makedirs(local_storage_path)

    remote_files = [
        {
            "path": "model.json",
            "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/apple/HomePod Mini/model.json",  # noqa: E501
        },
    ]

    mock_aioresponse.get(
        re.compile(rf"{ENDPOINT_DOWNLOAD}/apple/HomePod.*"),
        status=200,
        payload=remote_files,
        repeat=True,
    )

    mock_aioresponse.get(
        remote_files[0]["url"],
        status=200,
        body="invalid json",
        repeat=True,
    )

    with pytest.raises(LibraryLoadingError):
        await remote_loader.load_model("apple", "HomePod Mini")


@pytest.mark.parametrize(
    "manufacturer,phrases,expected_models,library_dir",
    [
        ("apple", {"HomePod (gen 2)"}, ["MQJ83"], None),
        ("apple", {"Non existing model"}, [], None),
        ("signify", {"LCA001", "LCT010"}, ["LCA001", "LCT010"], None),
        ("signify", {"lca001"}, ["LCA001"], None),
        ("test_manu", {"CCT Light"}, ["model1", "model2"], "multi_profile"),
        ("eq-3", {"HMIP-PSM"}, ["HmIP-PSM"], None),
        ("shelly", {"Shelly 1PM mini gen3"}, ["S3SW-001P8EU"], None),
    ],
)
@pytest.mark.skip_remote_loader_mocking
async def test_find_model(
    hass: HomeAssistant,
    manufacturer: str,
    phrases: set[str],
    expected_models: list[str],
    library_dir: str,
) -> None:
    with patch(
        "custom_components.powercalc.power_profile.loader.remote.RemoteLoader.load_library_json",
    ) as mock_load_lib:

        def load_library_json(*_args: object) -> dict:
            library_path = (
                get_test_config_dir(f"library_mock/{library_dir}/library.json")
                if library_dir
                else get_library_json_path()
            )
            with open(library_path) as f:
                return json.load(f)

        mock_load_lib.side_effect = load_library_json

        loader = RemoteLoader(hass)
        loader.retry_timeout = 0
        await loader.initialize()
        actual_models = await loader.find_model(manufacturer, phrases)
        assert sorted(actual_models) == expected_models


async def test_initialize_clears_cached_library_lookups(hass: HomeAssistant) -> None:
    first_library = {
        "manufacturers": [
            {
                "name": "Test",
                "dir_name": "test",
                "models": [
                    {
                        "id": "old_model",
                        "name": "Old Model",
                        "device_type": "light",
                    },
                ],
            },
        ],
    }
    second_library = {
        "manufacturers": [
            {
                "name": "Test",
                "dir_name": "test",
                "models": [
                    {
                        "id": "new_model",
                        "name": "New Model",
                        "device_type": "light",
                    },
                ],
            },
        ],
    }

    with patch(
        "custom_components.powercalc.power_profile.loader.remote.RemoteLoader.load_library_json",
        new_callable=AsyncMock,
        side_effect=[first_library, second_library],
    ):
        loader = RemoteLoader(hass)

        await loader.initialize()
        assert await loader.find_model("test", {"old_model"}) == ["old_model"]
        assert await loader.get_model_listing("test", {DeviceType.LIGHT}) == {("old_model", "Old Model")}

        await loader.initialize()
        assert await loader.find_model("test", {"old_model"}) == []
        assert await loader.find_model("test", {"new_model"}) == ["new_model"]
        assert await loader.get_model_listing("test", {DeviceType.LIGHT}) == {("new_model", "New Model")}


def clear_storage_dir(storage_path: str) -> None:
    if not os.path.exists(storage_path):
        return
    shutil.rmtree(storage_path, ignore_errors=True)


async def test_multiple_manufacturer_aliases(hass: HomeAssistant, mock_aioresponse: aioresponses) -> None:
    mock_aioresponse.get(
        ENDPOINT_LIBRARY,
        status=200,
        payload={
            "manufacturers": [
                {
                    "name": "manufacturer1",
                    "dir_name": "manufacturer1",
                    "aliases": ["my-alias"],
                    "models": [
                        {
                            "id": "model1",
                            "device_type": "light",
                            "updated_at": "2021-01-01T00:00:00",
                        },
                    ],
                },
                {
                    "name": "manufacturer2",
                    "dir_name": "manufacturer2",
                    "aliases": ["my-alias"],
                    "models": [
                        {
                            "id": "model1",
                            "device_type": "light",
                            "updated_at": "2021-01-01T00:00:00",
                        },
                    ],
                },
            ],
        },
    )

    library = await ProfileLibrary.factory(hass)

    manufacturers = await library.find_manufacturers("my-alias")
    assert manufacturers == {"manufacturer1", "manufacturer2"}
    manufacturers = await library.find_manufacturers("MY-ALIAS")
    assert manufacturers == {"manufacturer1", "manufacturer2"}

    model_listing = await library.get_model_listing("my-alias", {DeviceType.LIGHT})
    assert len(model_listing) == 2

    models = await library.find_models(ModelInfo("my-alias", "model1"))
    assert sorted(models) == [ModelInfo("manufacturer1", "model1"), ModelInfo("manufacturer2", "model1")]
    models = await library.find_models(ModelInfo("MY-ALIAS", "model1"))
    assert sorted(models) == [ModelInfo("manufacturer1", "model1"), ModelInfo("manufacturer2", "model1")]


@pytest.mark.parametrize(
    "version,expect_model",
    [
        ("1.50.0", True),
        ("0.40.0", False),
    ],
)
async def test_min_version(hass: HomeAssistant, version: str, expect_model: bool) -> None:
    with patch(
        "custom_components.powercalc.power_profile.loader.remote.RemoteLoader.load_library_json",
    ) as mock_load_lib:

        def load_library_json(*_args: object) -> dict:
            with open(get_test_config_dir("library_mock/min_version/library.json")) as f:
                return json.load(f)

        mock_load_lib.side_effect = load_library_json

        with patch(
            "custom_components.powercalc.power_profile.loader.remote.async_get_integration",
            new=AsyncMock(return_value=Mock(version=AwesomeVersion(version))),
        ):
            loader = RemoteLoader(hass)
            await loader.initialize()

            models = await loader.get_model_listing("test_manu", None)
            if expect_model:
                assert ("min_version", "Test profile") in models
            else:
                assert ("min_version", "Test profile") not in models
