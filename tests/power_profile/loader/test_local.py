import logging

import pytest
from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY
from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType
from tests.common import get_test_config_dir, get_test_profile_dir, run_powercalc_setup


async def test_broken_lib_by_identical_model_alias(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = LocalLoader(hass, get_test_profile_dir("double_model"))
    with caplog.at_level(logging.ERROR):
        await loader.initialize()
    assert "Double entry manufacturer/model in custom library:" in caplog.text


async def test_broken_lib_by_identical_alias_alias(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = LocalLoader(hass, get_test_profile_dir("double_alias"))
    with caplog.at_level(logging.ERROR):
        await loader.initialize()
        assert "Double entry manufacturer/model in custom library" in caplog.text


async def test_broken_lib_by_missing_model_json(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    loader = LocalLoader(hass, get_test_profile_dir("missing_model_json"))
    with caplog.at_level(logging.ERROR):
        await loader.initialize()
        assert "model.json should exist in" in caplog.text


@pytest.mark.parametrize(
    "manufacturer,search,expected",
    [
        ["tp-link", {"HS300"}, {"HS300"}],
        ["TP-link", {"HS300"}, {"HS300"}],
        ["tp-link", {"hs300"}, {"HS300"}],
        ["TP-link", {"hs300"}, {"HS300"}],
        ["tp-link", {"HS400"}, {"HS400"}],  # alias
        ["tp-link", {"hs400"}, {"HS400"}],  # alias
        ["tp-link", {"Hs500"}, {"hs500"}],  # alias
        ["tp-link", {"bla"}, set()],
        ["foo", {"bar"}, set()],
        ["casing", {"CaSinG- Test"}, {"CaSinG- Test"}],
        ["casing", {"CasinG- test"}, {"CaSinG- Test"}],
        ["casing", {"CASING- TEST"}, {"CaSinG- Test"}],
        ["hidden-directories", {".test"}, set()],
        ["hidden-directories", {".hidden_model"}, set()],
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


async def test_load_model_returns_none_when_model_not_found(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert await loader.load_model("tp-link", "bar") is None


# Test find_manufacturer
@pytest.mark.parametrize(
    "manufacturer,expected",
    [
        ["tp-link", {"tp-link"}],
        ["TP-Link", {"tp-link"}],
        ["foo", set()],
    ],
)
async def test_find_manufacturers(hass: HomeAssistant, manufacturer: str, expected: str | None) -> None:
    loader = await _create_loader(hass)
    assert expected == await loader.find_manufacturers(manufacturer)


async def test_get_manufacturer_listing(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert await loader.get_manufacturer_listing(None) == {"tp-link", "tasmota", "test", "hidden-directories", "casing"}
    assert "tp-link" in await loader.get_manufacturer_listing({DeviceType.SMART_SWITCH})
    assert "tp-link" in await loader.get_manufacturer_listing({DeviceType.LIGHT})
    assert "tp-link" not in await loader.get_manufacturer_listing({DeviceType.COVER})


async def test_get_model_listing(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert "HS300" in await loader.get_model_listing("tp-link", {DeviceType.SMART_SWITCH})
    assert "light20" not in await loader.get_model_listing("tp-link", {DeviceType.SMART_SWITCH})
    assert "light20" in await loader.get_model_listing("tp-link", {DeviceType.LIGHT})
    assert {"HS300", "HS400", "hs500", "light20"} == await loader.get_model_listing("tp-link", None)
    assert "HS400" in await loader.get_model_listing("tp-link", {DeviceType.SMART_SWITCH})
    assert "HS400" not in await loader.get_model_listing("tp-link", {DeviceType.LIGHT})
    assert "test" in await loader.get_model_listing("Tasmota", {DeviceType.LIGHT})
    assert ".test" not in await loader.get_model_listing("hidden-directories", {DeviceType.LIGHT})


async def test_get_model_listing_unknown_manufacturer(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert not await loader.get_model_listing("foo", {DeviceType.LIGHT})


async def test_custom_model_directory(hass: HomeAssistant) -> None:
    """
    Test that we can setup a virtual power sensor using a custom model directory.
    The source entity has no model and/or manufacturer information set.
    Verify that the power profile is loaded from the custom model directory correctly, and sensors are created.
    """

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("fixed"),
        },
    )

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "50.00"


async def _create_loader(hass: HomeAssistant) -> LocalLoader:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    return loader
