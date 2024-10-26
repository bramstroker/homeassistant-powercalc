import logging

import pytest
from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType
from tests.common import get_test_config_dir


async def test_broken_lib_by_identical_model_alias(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles_lib_broken/double-model"))
    with pytest.raises(LibraryLoadingError) as excinfo:
        await loader.initialize()
    assert "Double entry manufacturer/model by model+alias in custom library:" in str(excinfo.value)


async def test_broken_lib_by_identical_alias_alias(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles_lib_broken/double-alias"))
    with pytest.raises(LibraryLoadingError) as excinfo:
        await loader.initialize()
    assert "Double entry manufacturer/model by alias+alias in custom library:" in str(excinfo.value)


@pytest.mark.parametrize(
    "manufacturer,search,expected",
    [
        ["tp-link", {"HS300"}, "HS300"],
        ["TP-link", {"HS300"}, "HS300"],
        ["tp-link", {"hs300"}, "HS300"],
        ["TP-link", {"hs300"}, "HS300"],
        ["tp-link", {"HS400"}, "HS400"],  # alias
        ["tp-link", {"hs400"}, "HS400"],  # alias
        ["tp-link", {"Hs500"}, "hs500"],  # alias
        ["tp-link", {"bla"}, None],
        ["foo", {"bar"}, None],
        ["casing", {"CaSinG- Test"}, "CaSinG- Test"],
        ["casing", {"CasinG- test"}, "CaSinG- Test"],
        ["casing", {"CASING- TEST"}, "CaSinG- Test"],
        ["hidden-directories", {".test"}, None],
        ["hidden-directories", {".hidden_model"}, None],
    ],
)
async def test_find_model(hass: HomeAssistant, manufacturer: str, search: set[str], expected: str | None) -> None:
    loader = await _create_loader(hass)
    found_model = await loader.find_model(manufacturer, search)
    assert found_model == expected


# Tests for load_model
async def test_load_model_raise_no_modeljson_exception(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles/test/nojson"), is_custom_directory=True)
    with pytest.raises(LibraryLoadingError) as excinfo:
        await loader.load_model("test", "nojson")
    assert "model.json not found for manufacturer" in str(excinfo.value)


async def test_load_model_returns_none_when_manufacturer_not_found(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert await loader.load_model("foo", "bar") is None


async def test_load_model_returns_warning_when_manufacturer_not_found(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = await _create_loader(hass)
    with caplog.at_level(logging.INFO):
        await loader.load_model("foo", "bar")
    assert "Manufacturer does not exist in custom library: foo" in caplog.text


async def test_load_model_returns_none_when_model_not_found(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert await loader.load_model("tp-link", "bar") is None


async def test_load_model_returns_warning_when_model_not_found(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = await _create_loader(hass)
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
    loader = await _create_loader(hass)
    assert expected == await loader.find_manufacturer(manufacturer)


async def test_get_manufacturer_listing(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert await loader.get_manufacturer_listing(None) == {"tp-link", "tasmota", "hidden-directories", "casing"}
    assert "tp-link" in await loader.get_manufacturer_listing(DeviceType.SMART_SWITCH)
    assert "tp-link" in await loader.get_manufacturer_listing(DeviceType.LIGHT)
    assert "tp-link" not in await loader.get_manufacturer_listing(DeviceType.COVER)


async def test_get_model_listing(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert "HS300" in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "light20" not in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "light20" in await loader.get_model_listing("tp-link", DeviceType.LIGHT)
    assert {"HS300", "HS400", "hs500", "light20"} == await loader.get_model_listing("tp-link", None)
    assert "HS400" in await loader.get_model_listing("tp-link", DeviceType.SMART_SWITCH)
    assert "HS400" not in await loader.get_model_listing("tp-link", DeviceType.LIGHT)
    assert "test" in await loader.get_model_listing("Tasmota", DeviceType.LIGHT)
    assert ".test" not in await loader.get_model_listing("hidden-directories", DeviceType.LIGHT)


async def test_get_model_listing_unknown_manufacturer(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert not await loader.get_model_listing("foo", DeviceType.LIGHT)


async def _create_loader(hass: HomeAssistant) -> LocalLoader:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    return loader
