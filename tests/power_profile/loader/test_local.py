import logging

from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY
from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.local import LocalLoader
from custom_components.powercalc.power_profile.power_profile import DeviceType, DiscoveryBy
from tests.common import assert_entity_state, get_test_config_dir, get_test_profile_dir, run_powercalc_setup, set_states


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
    with caplog.at_level(logging.WARNING):
        await loader.initialize()
        assert "model.json should exist in" in caplog.text


@pytest.mark.parametrize(
    "manufacturer,search,expected",
    [
        ["tp-link", {"HS300"}, ["HS300"]],
        ["TP-link", {"HS300"}, ["HS300"]],
        ["tp-link", {"hs300"}, ["HS300"]],
        ["TP-link", {"hs300"}, ["HS300"]],
        ["tp-link", {"HS400"}, ["HS400"]],  # alias
        ["tp-link", {"hs400"}, ["HS400"]],  # alias
        ["tp-link", {"Hs500"}, ["hs500"]],  # alias
        ["tp-link", {"bla"}, []],
        ["foo", {"bar"}, []],
        ["casing", {"CaSinG- Test"}, ["CaSinG- Test"]],
        ["casing", {"CasinG- test"}, ["CaSinG- Test"]],
        ["casing", {"CASING- TEST"}, ["CaSinG- Test"]],
        ["hidden-directories", {".test"}, []],
        ["hidden-directories", {".hidden_model"}, []],
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
    assert await loader.get_manufacturer_listing(None) == {
        ("tp-link", "tp-link"),
        ("tasmota", "tasmota"),
        ("test", "test"),
        ("hidden-directories", "hidden-directories"),
        ("casing", "casing"),
    }
    assert ("tp-link", "tp-link") in await loader.get_manufacturer_listing({DeviceType.SMART_SWITCH})
    assert ("tp-link", "tp-link") in await loader.get_manufacturer_listing({DeviceType.LIGHT})
    assert ("tp-link", "tp-link") not in await loader.get_manufacturer_listing({DeviceType.COVER})
    assert ("test", "test") in await loader.get_manufacturer_listing(None, DiscoveryBy.DEVICE)
    assert ("tasmota", "tasmota") not in await loader.get_manufacturer_listing(None, DiscoveryBy.DEVICE)


async def test_get_model_listing(hass: HomeAssistant) -> None:
    loader = await _create_loader(hass)
    assert ("HS300", "IKEA Control outlet") in await loader.get_model_listing("tp-link", {DeviceType.SMART_SWITCH})
    assert ("light20", "IKEA Control outlet") not in await loader.get_model_listing("tp-link", {DeviceType.SMART_SWITCH})
    assert ("light20", "IKEA Control outlet") in await loader.get_model_listing("tp-link", {DeviceType.LIGHT})
    assert {
        ("HS300", "IKEA Control outlet"),
        ("HS400", "IKEA Control outlet"),
        ("hs500", "IKEA Control outlet"),
        ("light20", "IKEA Control outlet"),
    } == await loader.get_model_listing("tp-link", None)
    assert ("HS400", "IKEA Control outlet") in await loader.get_model_listing("tp-link", {DeviceType.SMART_SWITCH})
    assert ("HS400", "IKEA Control outlet") not in await loader.get_model_listing("tp-link", {DeviceType.LIGHT})
    assert ("test", "Fixed mode profile") in await loader.get_model_listing("Tasmota", {DeviceType.LIGHT})
    assert (".test", ".test") not in await loader.get_model_listing("hidden-directories", {DeviceType.LIGHT})
    device_models = await loader.get_model_listing("test", None, DiscoveryBy.DEVICE)
    assert any(model_id == "multi_switch" for model_id, _ in device_models)
    assert not any(model_id == "linked_profile_fixed" for model_id, _ in device_models)


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

    await set_states(hass, [("switch.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "50.00")


async def _create_loader(hass: HomeAssistant) -> LocalLoader:
    loader = LocalLoader(hass, get_test_config_dir("powercalc/profiles"))
    await loader.initialize()
    return loader
