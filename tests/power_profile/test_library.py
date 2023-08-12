import logging

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.aliases import MANUFACTURER_IKEA, MANUFACTURER_SIGNIFY
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from tests.common import get_test_profile_dir


async def test_manufacturer_listing(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    manufacturers = library.get_manufacturer_listing()
    assert "signify" in manufacturers
    assert "ikea" in manufacturers
    assert "bladiebla" not in manufacturers


async def test_model_listing(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    models = library.get_model_listing("signify")
    assert "LCT010" in models
    assert "LCA007" in models


async def test_get_subprofile_listing(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    profile = await library.get_profile(ModelInfo("yeelight", "YLDL01YL"))
    sub_profiles = profile.get_sub_profiles()
    assert sub_profiles == ["ambilight", "downlight"]


async def test_get_subprofile_listing_empty_list(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    profile = await library.get_profile(ModelInfo("signify", "LCT010"))
    sub_profiles = profile.get_sub_profiles()
    assert sub_profiles == []


async def test_non_existing_manufacturer_returns_empty_model_list(
    hass: HomeAssistant,
) -> None:
    library = ProfileLibrary(hass)
    assert not library.get_model_listing("foo")


async def test_get_profile(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    profile = await library.get_profile(ModelInfo("signify", "LCT010"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile.model == "LCT010"
    assert profile.get_model_directory().endswith("signify/LCT010")


async def test_get_profile_with_full_manufacturer_name(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    profile = await library.get_profile(ModelInfo(MANUFACTURER_SIGNIFY, "LCT010"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile.get_model_directory().endswith("signify/LCT010")


async def test_get_profile_with_model_alias(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    profile = await library.get_profile(
        ModelInfo(MANUFACTURER_IKEA, "TRADFRI bulb E14 WS opal 400lm"),
    )
    assert profile.get_model_directory().endswith("ikea/LED1536G5")


async def test_get_non_existing_profile(hass: HomeAssistant) -> None:
    library = ProfileLibrary(hass)
    profile = await library.get_profile(ModelInfo("foo", "bar"))
    assert not profile


async def test_hidden_directories_are_skipped_from_model_listing(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    library = ProfileLibrary(hass)
    profiles = await library.get_profiles_by_manufacturer(
        get_test_profile_dir("hidden-directories"),
    )
    assert len(profiles) == 1
    assert len(caplog.records) == 0


async def test_exception_is_raised_when_no_model_json_present(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    library = ProfileLibrary(hass)
    await library.create_power_profile(
        ModelInfo("foo", "bar"),
        get_test_profile_dir("no-model-json"),
    )
    assert "model.json file not found in directory" in caplog.text
