import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType
from tests.common import get_test_config_dir


async def test_get_manufacturer_listing(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    assert "tp-link" in await loader.get_manufacturer_listing(DeviceType.SMART_SWITCH)


async def test_get_model_listing(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    assert "HS300" in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "test" in await loader.get_model_listing("Tasmota", DeviceType.LIGHT)


async def test_get_model_listing_unknown_manufacturer(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    assert not await loader.get_model_listing("foo", DeviceType.LIGHT)


async def test_load_model_returns_none_when_not_found(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    assert not await loader.load_model("foo", "bar")


@pytest.mark.parametrize(
    "manufacturer,search,expected",
    [
        ["tp-link", {"HS300"}, "HS300"],
        ["tp-link", {"bla"}, None],
        ["foo", {"bar"}, None],
        ["casing", {"CaSinG- Test"}, "CaSinG- Test"],
        ["casing", {"CasinG- test"}, "CaSinG- Test"],
        ["casing", {"CASING- TEST"}, "CaSinG- Test"],
    ],
)
async def test_find_model(hass: HomeAssistant, manufacturer: str, search: set[str], expected: str | None) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    found_model = await loader.find_model(manufacturer, search)
    assert found_model == expected

    # Also check that loading the model works
    found_model and loader.load_model(manufacturer, found_model)


@pytest.mark.parametrize(
    "manufacturer,expected",
    [
        ["tp-link", "tp-link"],
        ["TP-Link", None],
        ["foo", None],
    ],
)
async def test_find_manufacturer(hass: HomeAssistant, manufacturer: str, expected: str | None) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    assert expected == await loader.find_manufacturer(manufacturer)
