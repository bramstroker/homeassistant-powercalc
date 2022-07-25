from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.library import ProfileLibrary
from custom_components.powercalc.aliases import (
    MANUFACTURER_IKEA,
    MANUFACTURER_SIGNIFY
)

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

async def test_model_directory(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    directory = library.get_model_directory("signify", "LCT010")
    assert directory.endswith("signify/LCT010")

async def test_model_directory_with_full_manufacturer_name(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    directory = library.get_model_directory(MANUFACTURER_SIGNIFY, "LCT010")
    assert directory.endswith("signify/LCT010")

async def test_model_directory_with_model_alias(hass: HomeAssistant):
    library = ProfileLibrary(hass)
    directory = library.get_model_directory(MANUFACTURER_IKEA, "TRADFRI bulb E14 WS opal 400lm")
    assert directory.endswith("ikea/LED1536G5")