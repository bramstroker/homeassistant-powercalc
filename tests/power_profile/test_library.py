from homeassistant.core import HomeAssistant

from custom_components.powercalc.aliases import MANUFACTURER_IKEA, MANUFACTURER_SIGNIFY
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary


async def test_manufacturer_listing(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    manufacturers = library.get_manufacturer_listing()
    assert "signify" in manufacturers
    assert "ikea" in manufacturers
    assert "bladiebla" not in manufacturers


async def test_model_listing(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    models = library.get_model_listing("signify")
    assert "LCT010" in models
    assert "LCA007" in models


async def test_non_existing_manufacturer_returns_empty_model_list(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    assert not library.get_model_listing("foo")


async def test_get_profile(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    profile = library.get_profile(ModelInfo("signify", "LCT010"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile.model == "LCT010" 
    assert profile._directory.endswith("signify/LCT010")


async def test_get_profile_with_full_manufacturer_name(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    profile = library.get_profile(ModelInfo(MANUFACTURER_SIGNIFY, "LCT010"))
    assert profile
    assert profile.manufacturer == "signify"
    assert profile._directory.endswith("signify/LCT010")


async def test_get_profile_with_model_alias(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    profile = library.get_profile(
        ModelInfo(
            MANUFACTURER_IKEA,
            "TRADFRI bulb E14 WS opal 400lm"
        )
    )
    assert profile._directory.endswith("ikea/LED1536G5")

async def test_get_non_existing_profile(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    profile = library.get_profile(ModelInfo("foo", "bar"))
    assert not profile