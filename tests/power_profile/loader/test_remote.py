import json
import os

import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant

from custom_components.powercalc.helpers import get_library_path
from custom_components.powercalc.power_profile.loader.remote import ENDPOINT_DOWNLOAD, RemoteLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType
from tests.common import get_test_profile_dir


@pytest.fixture
def mock_aioresponse() -> aioresponses:
    with aioresponses() as m:
        yield m


@pytest.mark.skip_remote_loader_mocking
async def test_download(hass: HomeAssistant, mock_aioresponse: aioresponses) -> None:
    """Mock the API response for the download of a profile."""
    remote_files = [
        {"path": "color_temp.csv.gz", "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/custom_components/powercalc/data/signify/LCA001/color_temp.csv.gz"},
        {"path": "hs.csv.gz", "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/custom_components/powercalc/data/signify/LCA001/hs.csv.gz"},
        {"path": "model.json", "url": "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/custom_components/powercalc/data/signify/LCA001/model.json"},
    ]

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/signify/LCA001",
        status=200,
        payload=remote_files,
    )

    for remote_file in remote_files:
        with open(get_test_profile_dir("signify-LCA001") + f"/{remote_file['path']}", "rb") as f:
            mock_aioresponse.get(
                remote_file["url"],
                status=200,
                body=f.read(),
            )

    loader = RemoteLoader(hass)
    storage_dir = get_test_profile_dir("download")
    await loader.download_profile("signify", "LCA001", storage_dir)

    for remote_file in remote_files:
        assert os.path.exists(os.path.join(storage_dir, remote_file["path"]))


async def test_get_manufacturer_listing(hass: HomeAssistant, mock_aioresponse: aioresponses) -> None:
    local_library_path = get_library_path("library.json")
    with open(local_library_path) as f:
        library_json = json.load(f)

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/library",
        status=200,
        payload=library_json,
    )

    loader = RemoteLoader(hass)
    await loader.initialize()
    manufacturers = await loader.get_manufacturer_listing(DeviceType.LIGHT)
    assert "signify" in manufacturers
    assert len(manufacturers) > 40


async def test_get_model_listing(hass: HomeAssistant, mock_aioresponse: aioresponses) -> None:
    local_library_path = get_library_path("library.json")
    with open(local_library_path) as f:
        library_json = json.load(f)

    mock_aioresponse.get(
        f"{ENDPOINT_DOWNLOAD}/library",
        status=200,
        payload=library_json,
    )

    loader = RemoteLoader(hass)
    await loader.initialize()
    models = await loader.get_model_listing("signify", DeviceType.LIGHT)
    assert "LCT010" in models
    assert len(models) > 40
