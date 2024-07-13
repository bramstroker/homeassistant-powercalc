import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.helpers import get_library_path
from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType


async def test_get_manufacturer_listing(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_library_path())
    assert "signify" in await loader.get_manufacturer_listing(DeviceType.LIGHT)


async def test_get_model_listing(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_library_path())
    assert "LCA001" in await loader.get_model_listing("signify", DeviceType.LIGHT)


async def test_get_model_listing_unknown_manufacturer(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_library_path())
    assert not await loader.get_model_listing("foo", DeviceType.LIGHT)


async def test_load_model_returns_none_when_not_found(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_library_path())
    assert not await loader.load_model("foo", "bar")


@pytest.mark.parametrize(
    "manufacturer,search,expected",
    [
        ["signify", {"LCA001"}, "LCA001"],
        ["signify", {"bla"}, None],
        ["foo", {"bar"}, None],
    ],
)
async def test_find_model(hass: HomeAssistant, manufacturer: str, search: set[str], expected: str | None) -> None:
    loader = LocalLoader(hass, get_library_path())
    assert expected == await loader.find_model(manufacturer, search)


@pytest.mark.parametrize(
    "manufacturer,expected",
    [
        ["signify", "signify"],
        ["Signify", None],
        ["foo", None],
    ],
)
async def test_find_manufacturer(hass: HomeAssistant, manufacturer: str, expected: str | None) -> None:
    loader = LocalLoader(hass, get_library_path())
    assert expected == await loader.find_manufacturer(manufacturer)
