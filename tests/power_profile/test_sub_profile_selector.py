from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
import pytest
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.errors import PowercalcSetupError
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.power_profile import PowerProfile
from custom_components.powercalc.power_profile.sub_profile_selector import ModelIdMatcher, SubProfileSelector
from tests.common import get_test_profile_dir


async def test_matcher_attribute(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        custom_directory=get_test_profile_dir("sub_profile_match_attribute"),
    )
    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        SourceEntity(entity_id="light.test", domain="light", object_id="test"),
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test", STATE_OFF)
    assert selector.select_sub_profile(state) == "a"

    state = State("light.test", STATE_ON, {"some": "a"})
    assert selector.select_sub_profile(state) == "a"

    state = State("light.test", STATE_ON, {"some": "b"})
    assert selector.select_sub_profile(state) == "b"


async def test_matcher_entity_id(hass: HomeAssistant) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        custom_directory=get_test_profile_dir("sub_profile_match_entity_id"),
    )
    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        SourceEntity(entity_id="light.test", domain="light", object_id="test"),
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test_nightlight", STATE_ON)
    assert selector.select_sub_profile(state) == "nightlight"

    state = State("light.test", STATE_ON)
    assert selector.select_sub_profile(state) == "default"


@pytest.mark.parametrize(
    "registry_entry,expected_profile",
    [
        (
            RegistryEntryWithDefaults(
                entity_id="switch.test",
                platform="tasmota",
                unique_id="111",
            ),
            "tasmota",
        ),
        (
            RegistryEntryWithDefaults(
                entity_id="switch.test",
                platform="shelly",
                unique_id="111",
            ),
            "default",
        ),
        (None, "default"),
    ],
)
async def test_matcher_integration(
    hass: HomeAssistant,
    registry_entry: RegistryEntry,
    expected_profile: str | None,
) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        custom_directory=get_test_profile_dir("sub_profile_match_integration"),
    )

    source_entity = SourceEntity(
        entity_id="switch.test",
        domain="switch",
        object_id="test",
        entity_entry=registry_entry,
    )

    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        source_entity,
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("switch.test", STATE_ON)
    assert selector.select_sub_profile(state) == expected_profile


@pytest.mark.parametrize(
    "model_id,expected_profile",
    [
        ("model-123", "sub1"),
        ("model-456", "sub2"),
        ("other", "default"),
    ],
)
async def test_matcher_model_id(
    hass: HomeAssistant,
    model_id: str,
    expected_profile: str,
) -> None:
    library = await ProfileLibrary.factory(hass)
    power_profile = await library.get_profile(
        ModelInfo("Test", "Test"),
        custom_directory=get_test_profile_dir("sub_profile_match_model_id"),
    )

    device_entry = DeviceEntry(id="abc", model_id=model_id)
    source_entity = SourceEntity(
        entity_id="light.test",
        domain="light",
        object_id="test",
        device_entry=device_entry,
    )

    selector = SubProfileSelector(
        hass,
        power_profile.sub_profile_select,
        source_entity,
    )
    assert len(selector.get_tracking_entities()) == 0

    state = State("light.test", STATE_ON)
    sub_profile = selector.select_sub_profile(state)
    assert sub_profile == expected_profile
    if sub_profile != "default":
        await power_profile.select_sub_profile(sub_profile)
        assert power_profile.sub_profile == expected_profile


async def test_matcher_model_id_no_device_entry() -> None:
    matcher = ModelIdMatcher("foo", "bar")
    assert matcher.match(State("light.test", STATE_ON), SourceEntity(entity_id="light.test", domain="light", object_id="test")) is None


async def test_exception_is_raised_when_invalid_sub_profile_matcher_supplied(
    hass: HomeAssistant,
) -> None:
    with pytest.raises(PowercalcSetupError):
        power_profile = PowerProfile(
            hass,
            manufacturer="Foo",
            model="Bar",
            directory="",
            json_data={
                "sub_profile_select": {
                    "matchers": [{"type": "invalid_type"}],
                    "default": "henkie",
                },
            },
        )
        SubProfileSelector(
            hass,
            power_profile.sub_profile_select,
            SourceEntity(entity_id="light.test", domain="light", object_id="test"),
        )
