import logging

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType
from tests.common import get_test_config_dir


# Test for find_model
@pytest.mark.parametrize(
    "manufacturer,search,expected",
    [
        ["tp-link", {"HS300"}, "hs300"],
        ["TP-link", {"HS300"}, "hs300"],
        ["tp-link", {"HS400"}, "hs400"],  # alias
        ["tp-link", {"Hs500"}, "hs500"],  # alias
        ["tp-link", {"bla"}, None],
        ["foo", {"bar"}, None],
        ["casing", {"CaSinG- Test"}, "casing- test"],
        ["casing", {"CasinG- test"}, "casing- test"],
        ["casing", {"CASING- TEST"}, "casing- test"],
        ["hidden-directories", {".test"}, None],
        ["hidden-directories", {".hidden_model"}, None],
    ],
)
async def test_find_model(hass: HomeAssistant, manufacturer: str, search: set[str], expected: str | None) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    found_model = await loader.find_model(manufacturer, search)
    assert found_model == expected


# Tests for load_model
async def test_load_model_returns_none_when_manufacturer_not_found(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    assert await loader.load_model("foo", "bar") is None


async def test_load_model_returns_warning_when_manufacturer_not_found(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    with caplog.at_level(logging.INFO):
        await loader.load_model("foo", "bar")
    assert "Manufacturer does not exist in custom library: foo" in caplog.text


async def test_load_model_returns_none_when_model_not_found(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    assert await loader.load_model("tp-link", "bar") is None


async def test_load_model_returns_warning_when_model_not_found(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    with caplog.at_level(logging.INFO):
        await loader.load_model("tp-link", "bar")
    assert "Model does not exist in custom library for manufacturer tp-link: bar" in caplog.text


# Test find_manufacturer
@pytest.mark.parametrize(
    "manufacturer,expected",
    [
        ["tp-link", "tp-link"],
        ["TP-Link", "tp-link"],
        ["foo", None],
    ],
)
async def test_find_manufacturer(hass: HomeAssistant, manufacturer: str, expected: str | None) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    assert expected == await loader.find_manufacturer(manufacturer)


async def test_get_manufacturer_listing(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    assert await loader.get_manufacturer_listing(None) == ["tp-link", "tasmota", "hidden-directories", "casing"]
    assert "tp-link" in await loader.get_manufacturer_listing(DeviceType.SMART_SWITCH)
    assert "tp-link" in await loader.get_manufacturer_listing(DeviceType.LIGHT)
    assert "tp-link" not in await loader.get_manufacturer_listing(DeviceType.COVER)


async def test_get_model_listing(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    assert "hs300" in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "light20" not in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "light20" in await loader.get_model_listing("tp-link", DeviceType.LIGHT)
    assert {"hs300", "hs400", "hs500", "light20"} == await loader.get_model_listing("tp-link", None)
    assert "hs400" in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "test" in await loader.get_model_listing("Tasmota", DeviceType.LIGHT)
    assert ".test" not in await loader.get_model_listing("hidden-directories", DeviceType.LIGHT)


async def test_get_model_listing_unknown_manufacturer(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    assert not await loader.get_model_listing("foo", DeviceType.LIGHT)
