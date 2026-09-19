from unittest.mock import MagicMock

from homeassistant_api import State
from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.errors import ApiConnectionError
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.hass import HassLightController
import pytest


@pytest.mark.parametrize(
    "attributes,min_mired,max_mired",
    [
        (
            {"min_color_temp_kelvin": 2202, "max_color_temp_kelvin": 6535},
            153,
            454,
        ),
        (
            {},
            MIN_MIRED,
            MAX_MIRED,
        ),
    ],
)
def test_get_light_info(hass_client: MagicMock, attributes: dict[str, int], min_mired: int, max_mired: int) -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes=attributes,
    )
    hass_client.get_state.return_value = mocked_state
    light_info = _get_instance(hass_client).get_light_info()
    assert light_info.get_min_mired() == min_mired
    assert light_info.get_max_mired() == max_mired


def test_effect_list(hass_client: MagicMock) -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes={"effect_list": ["A", "B", "C"]},
    )
    hass_client.get_state.return_value = mocked_state
    assert _get_instance(hass_client).get_effect_list() == ["A", "B", "C"]


def test_effect_list_handles_null_value(hass_client: MagicMock) -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes={"effect_list": None},
    )
    hass_client.get_state.return_value = mocked_state

    assert _get_instance(hass_client).get_effect_list() == []


def test_has_effect_support(hass_client: MagicMock) -> None:
    hass_controller = _get_instance(hass_client)
    assert hass_controller.has_effect_support()


@pytest.mark.parametrize(
    "mode,call_kwargs,trigger_service_body",
    [
        (
            LutMode.BRIGHTNESS,
            {"bri": 100},
            {"brightness": 100, "transition": 0},
        ),
        (
            LutMode.COLOR_TEMP,
            {"bri": 100, "ct": 100},
            {"brightness": 100, "color_temp_kelvin": 10000, "transition": 0},
        ),
        (
            LutMode.HS,
            {"bri": 100, "hue": 100, "sat": 100},
            {"brightness": 100, "hs_color": [0.5493247882810712, 39.21568627450981], "transition": 0},
        ),
        (
            LutMode.EFFECT,
            {"bri": 100, "effect": "A"},
            {"brightness": 100, "effect": "A"},
        ),
        (
            LutMode.WHITE,
            {"bri": 100},
            {"white": 100},
        ),
    ],
)
def test_change_light_state(
    hass_client: MagicMock, mode: LutMode, call_kwargs: dict, trigger_service_body: dict
) -> None:
    _get_instance(hass_client).change_light_state(mode, on=True, **call_kwargs)
    hass_client.trigger_service.assert_called_once_with(
        "light", "turn_on", entity_id="light.test", **trigger_service_body
    )


def test_turn_off(hass_client: MagicMock) -> None:
    _get_instance(hass_client).change_light_state(LutMode.BRIGHTNESS, on=False)
    hass_client.trigger_service.assert_called_once_with("light", "turn_off", entity_id="light.test")


@pytest.mark.parametrize("connection_error", [HomeassistantAPIError("Error"), BrokenPipeError(32, "Broken pipe")])
def test_change_light_state_error(hass_client: MagicMock, connection_error: Exception) -> None:
    hass_client.trigger_service.side_effect = connection_error
    controller = _get_instance(hass_client)
    with pytest.raises(ApiConnectionError) as error:
        controller.change_light_state(LutMode.BRIGHTNESS, on=True, bri=100)

    assert error.value.__cause__ is connection_error


def test_connection_validation(hass_client: MagicMock) -> None:
    hass_client.get_config.side_effect = HomeassistantAPIError("Error")
    with pytest.raises(ApiConnectionError):
        HassLightController(hass_client, 0, entity_ids=["light.test"])


def test_controller_requires_an_entity(hass_client: MagicMock) -> None:
    with pytest.raises(ValueError, match="at least one entity"):
        HassLightController(hass_client, 0, entity_ids=[])


def test_multiple_entities_are_targeted_together_with_their_common_capabilities(hass_client: MagicMock) -> None:
    hass_client.get_state.side_effect = [
        State(
            entity_id="light.one",
            state="on",
            attributes={"min_color_temp_kelvin": 2000, "max_color_temp_kelvin": 5000},
        ),
        State(
            entity_id="light.two",
            state="on",
            attributes={"min_color_temp_kelvin": 2500, "max_color_temp_kelvin": 6500},
        ),
        State(entity_id="light.one", state="on", attributes={"effect_list": ["one", "shared"]}),
        State(entity_id="light.two", state="on", attributes={"effect_list": ["shared", "two"]}),
    ]
    controller = HassLightController(hass_client, 0, entity_ids=["light.one", "light.two"])

    controller.change_light_state(LutMode.BRIGHTNESS, bri=100)
    hass_client.trigger_service.assert_called_once_with(
        "light",
        "turn_on",
        entity_id=["light.one", "light.two"],
        brightness=100,
        transition=0,
    )
    info = controller.get_light_info()
    assert (info.min_mired, info.max_mired) == (200, 400)
    assert controller.get_effect_list() == ["shared"]


def test_controller_waits_for_transition_only_after_turning_on(hass_client: MagicMock) -> None:
    wait = MagicMock()
    controller = HassLightController(hass_client, 3, entity_ids=["light.test"], wait=wait)

    controller.change_light_state(LutMode.BRIGHTNESS, bri=100)
    wait.assert_called_once_with(3)
    controller.change_light_state(LutMode.BRIGHTNESS, on=False)
    wait.assert_called_once_with(3)
    controller.close()


def test_controller_does_not_wait_when_service_call_fails(hass_client: MagicMock) -> None:
    failure = OSError("Disconnected")
    hass_client.trigger_service.side_effect = failure
    wait = MagicMock()
    controller = HassLightController(hass_client, 3, entity_ids=["light.test"], wait=wait)

    with pytest.raises(ApiConnectionError, match="Failed to change light state") as error:
        controller.change_light_state(LutMode.BRIGHTNESS, bri=100)

    assert error.value.__cause__ is failure
    wait.assert_not_called()


def _get_instance(client: MagicMock) -> HassLightController:
    return HassLightController(
        client,
        0,
        entity_ids=["light.test"],
    )
