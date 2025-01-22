import logging
import os.path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_DISABLE_LIBRARY_DOWNLOAD
from custom_components.powercalc.power_profile.error import LibraryError, LibraryLoadingError
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.loader.composite import CompositeLoader
from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.loader.remote import RemoteLoader
from tests.common import get_test_config_dir, get_test_profile_dir, run_powercalc_setup


async def test_manufacturer_listing(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    manufacturers = await library.get_manufacturer_listing()
    assert "signify" in manufacturers
    assert "ikea" in manufacturers
    assert "bladiebla" not in manufacturers


@pytest.mark.parametrize(
    "manufacturer,expected_models",
    [
        ("signify", ["LCT010", "LCA007"]),
        ("Signify Netherlands B.V.", ["LCT010"]),
    ],
)
async def test_model_listing(hass: HomeAssistant, manufacturer: str, expected_models: list[str]) -> None:
    hass.config.config_dir = get_test_config_dir()
    library = await ProfileLibrary.factory(hass)
    await library.get_model_listing(manufacturer)
    models = await library.get_model_listing(manufacturer)  # Trigger twice to test cache
    for model in expected_models:
        assert model in models


@pytest.mark.parametrize(
    "model_info,expected_models",
    [
        (ModelInfo("signify", "LCT010"), {"LCT010"}),
        (ModelInfo("lidl", "HG06106A/HG06104A"), {"HG06104A", "HG06106A"}),
    ],
)
async def test_find_models(hass: HomeAssistant, model_info: ModelInfo, expected_models: set[str]) -> None:
    library = await ProfileLibrary.factory(hass)
    models = await library.find_models(model_info)
    assert {model.model for model in models} == expected_models


async def test_get_sub_profile_listing(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("yeelight", "YLDL01YL"))
    sub_profiles = [profile[0] for profile in await profile.get_sub_profiles()]
    assert sub_profiles == [
        "ambilight",
        "downlight",
    ]


async def test_get_subprofile_listing_empty_list(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("signify", "LCT010"))
    sub_profiles = await profile.get_sub_profiles()
    assert sub_profiles == []


async def test_non_existing_manufacturer_returns_empty_model_list(
    hass: HomeAssistant,
) -> None:
    library = await ProfileLibrary.factory(hass)
    assert not await library.get_model_listing("foo")


@pytest.mark.parametrize(
    "model_info,expected_manufacturer,expected_model",
    [
        (ModelInfo("signify", "LCT010"), "signify", "LCT010"),
        (ModelInfo("signify", "LCA001"), "signify", "LCA001"),
        (ModelInfo("signify", "Hue go (LLC020)"), "signify", "LLC020"),
        (ModelInfo("ikea", "TRADFRI bulb E14 WS opal 400lm"), "ikea", "LED1536G5"),
        (ModelInfo("signify", "Hue go", "LLC020"), "signify", "LLC020"),
    ],
)
async def test_get_profile(
    hass: HomeAssistant,
    model_info: ModelInfo,
    expected_manufacturer: str,
    expected_model: str,
) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(model_info)
    assert profile
    assert profile.manufacturer == expected_manufacturer
    assert profile.model == expected_model
    assert profile.get_model_directory().endswith(f"{expected_manufacturer}/{expected_model}")


async def test_get_non_existing_profile_raises_exception(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    with pytest.raises(LibraryError):
        await library.get_profile(ModelInfo("foo", "bar"))


async def test_hidden_directories_are_skipped_from_model_listing(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hass.config.config_dir = get_test_config_dir()
    caplog.set_level(logging.ERROR)
    library = await ProfileLibrary.factory(hass)
    models = await library.get_model_listing("hidden-directories")
    assert len(models) == 1
    assert len(caplog.records) == 0


async def test_exception_is_raised_when_no_model_json_present(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    library = await ProfileLibrary.factory(hass)
    with pytest.raises(LibraryLoadingError):
        await library.create_power_profile(
            ModelInfo("foo", "bar"),
            get_test_profile_dir("no_model_json"),
        )


async def test_create_power_profile_raises_library_error(hass: HomeAssistant) -> None:
    """When no loader is able to load the model, a LibraryError should be raised."""
    mock_loader = LocalLoader(hass, "")
    mock_loader.load_model = AsyncMock(return_value=None)
    mock_loader.find_manufacturers = AsyncMock(return_value="signify")
    mock_loader.find_model = AsyncMock(return_value=ModelInfo("signify", "LCT010"))
    library = ProfileLibrary(hass, loader=mock_loader)
    await library.initialize()
    with pytest.raises(LibraryError):
        await library.create_power_profile(ModelInfo("signify", "LCT010"))


async def test_create_power_raise_library_error_when_model_not_found(hass: HomeAssistant) -> None:
    """When model is not found in library a LibraryError should be raised"""
    mock_loader = LocalLoader(hass, "")
    mock_loader.load_model = AsyncMock(return_value=None)
    mock_loader.find_manufacturers = AsyncMock(return_value="signify")
    mock_loader.find_model = AsyncMock(return_value=[])
    library = ProfileLibrary(hass, loader=mock_loader)
    await library.initialize()
    with pytest.raises(LibraryError):
        await library.create_power_profile(ModelInfo("signify", "LCT010"))


async def test_create_power_raise_library_error_when_manufacturer_not_found(hass: HomeAssistant) -> None:
    """When model is not found in library a LibraryError should be raised"""
    mock_loader = LocalLoader(hass, "")
    mock_loader.load_model = AsyncMock(return_value=None)
    mock_loader.find_manufacturers = AsyncMock(return_value=None)
    library = ProfileLibrary(hass, loader=mock_loader)
    await library.initialize()
    with pytest.raises(LibraryError):
        await library.create_power_profile(ModelInfo("signify", "LCT010"))


async def test_download_feature_can_be_disabled(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISABLE_LIBRARY_DOWNLOAD: True,
        },
    )

    library = await ProfileLibrary.factory(hass)
    composite_loader: CompositeLoader = library.get_loader()
    has_remote_loader = any(isinstance(loader, RemoteLoader) for loader in composite_loader.loaders)
    assert not has_remote_loader


async def test_linked_profile_loading(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("signify", "LCA007"))
    assert profile.linked_profile == "signify/LCA006"

    assert profile.get_model_directory().endswith("signify/LCA006")

    assert os.path.exists(os.path.join(profile.get_model_directory(), "color_temp.csv.gz"))


async def test_linked_profile_loading_failed(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)

    remote_loader_class = "custom_components.powercalc.power_profile.loader.remote.RemoteLoader"
    with patch(f"{remote_loader_class}.load_model") as mock_load_model:

        async def async_load_model_patch(manufacturer: str, __: str) -> tuple[dict, str] | None:
            if manufacturer == "foo":
                return None

            return {
                "manufacturer": "signify",
                "model": "LCA001",
                "linked_profile": "foo/bar",
            }, ""

        mock_load_model.side_effect = async_load_model_patch

        with pytest.raises(LibraryError):
            await library.get_profile(ModelInfo("signify", "LCA001"))
