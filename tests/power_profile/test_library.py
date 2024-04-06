import logging
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.aliases import MANUFACTURER_IKEA, MANUFACTURER_SIGNIFY
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.loader.local import LocalLoader
from tests.common import get_test_config_dir, get_test_profile_dir


async def test_manufacturer_listing(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    manufacturers = await library.get_manufacturer_listing()
    assert "signify" in manufacturers
    assert "ikea" in manufacturers
    assert "bladiebla" not in manufacturers


async def test_model_listing(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    await library.get_model_listing("signify")
    models = await library.get_model_listing("signify")  # Trigger twice to test cache
    assert "LCT010" in models
    assert "LCA007" in models


async def test_model_listing_full_manufacturer_name(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    models = await library.get_model_listing("Signify Netherlands B.V.")
    assert "LCT010" in models


async def test_get_subprofile_listing(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("yeelight", "YLDL01YL"))
    sub_profiles = profile.get_sub_profiles()
    assert sub_profiles == ["ambilight", "downlight"]


async def test_get_subprofile_listing_empty_list(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("signify", "LCT010"))
    sub_profiles = profile.get_sub_profiles()
    assert sub_profiles == []


async def test_non_existing_manufacturer_returns_empty_model_list(
    hass: HomeAssistant,
) -> None:
    library = await ProfileLibrary.factory(hass)
    assert not await library.get_model_listing("foo")


async def test_get_profile(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("signify", "LCT010"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile.model == "LCT010"
    assert profile.get_model_directory().endswith("signify/LCT010")


async def test_get_profile_with_full_model_name(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo(MANUFACTURER_SIGNIFY, "LCA001"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile.get_model_directory().endswith("signify/LCA001")


async def test_get_profile_with_full_manufacturer_name(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo(MANUFACTURER_SIGNIFY, "Hue go (LLC020)"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile.get_model_directory().endswith("signify/LLC020")


async def test_get_profile_with_model_alias(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(
        ModelInfo(MANUFACTURER_IKEA, "TRADFRI bulb E14 WS opal 400lm"),
    )
    assert profile.get_model_directory().endswith("ikea/LED1536G5")


async def test_get_non_existing_profile(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    profile = await library.get_profile(ModelInfo("foo", "bar"))
    assert not profile


async def test_hidden_directories_are_skipped_from_model_listing(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hass.config.config_dir = get_test_config_dir()
    caplog.set_level(logging.ERROR)
    library = await ProfileLibrary.factory(hass)
    models = await library.get_model_listing(
        get_test_profile_dir("hidden-directories"),
    )
    assert len(models) == 1
    assert len(caplog.records) == 0


async def test_exception_is_raised_when_no_model_json_present(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    library = await ProfileLibrary.factory(hass)
    await library.create_power_profile(
        ModelInfo("foo", "bar"),
        get_test_profile_dir("no-model-json"),
    )
    assert "model.json not found" in caplog.text


async def test_create_power_profile_raises_library_error(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """When no loader is able to load the model, a LibraryError should be raised."""
    caplog.set_level(logging.ERROR)
    mock_loader = LocalLoader(hass, "")
    mock_loader.load_model = AsyncMock(return_value=None)
    mock_loader.find_model = AsyncMock(return_value=ModelInfo("signify", "LCT010"))
    library = ProfileLibrary(hass, loader=mock_loader)
    await library.initialize()
    await library.create_power_profile(ModelInfo("signify", "LCT010"))

    assert "Problem loading model" in caplog.text
