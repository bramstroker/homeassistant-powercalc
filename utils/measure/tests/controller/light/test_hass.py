from unittest.mock import MagicMock

from homeassistant_api import State
from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.errors import ApiConnectionError
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.hass import HassLightController
from measure.home_assistant import HomeAssistantManager
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
def test_get_light_info(attributes: dict[str, int], min_mired: int, max_mired: int) -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes=attributes,
    )
    client = _mock_client()
    client.get_state.return_value = mocked_state
    light_info = _get_instance(client).get_light_info()
    assert light_info.get_min_mired() == min_mired
    assert light_info.get_max_mired() == max_mired


def test_effect_list() -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes={"effect_list": ["A", "B", "C"]},
    )
    client = _mock_client()
    client.get_state.return_value = mocked_state
    assert _get_instance(client).get_effect_list() == ["A", "B", "C"]


def test_has_effect_support() -> None:
    hass_controller = _get_instance()
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
    ],
)
def test_change_light_state(mode: LutMode, call_kwargs: dict, trigger_service_body: dict) -> None:
    client = _mock_client()
    _get_instance(client).change_light_state(mode, on=True, **call_kwargs)
    client.trigger_service.assert_called_once_with("light", "turn_on", entity_id="light.test", **trigger_service_body)


def test_turn_off() -> None:
    client = _mock_client()
    _get_instance(client).change_light_state(LutMode.BRIGHTNESS, on=False)
    client.trigger_service.assert_called_once_with("light", "turn_off", entity_id="light.test")


@pytest.mark.parametrize("connection_error", [HomeassistantAPIError("Error"), BrokenPipeError(32, "Broken pipe")])
def test_change_light_state_error(connection_error: Exception) -> None:
    client = _mock_client()
    client.trigger_service.side_effect = connection_error
    controller = _get_instance(client)
    with pytest.raises(ApiConnectionError) as error:
        controller.change_light_state(LutMode.BRIGHTNESS, on=True, bri=100)

    assert error.value.__cause__ is connection_error


def test_connection_validation() -> None:
    client = _mock_client()
    client.get_config.side_effect = HomeassistantAPIError("Error")
    with pytest.raises(ApiConnectionError):
        HassLightController(client, 0, entity_ids=["light.test"])


def test_controller_requires_an_entity() -> None:
    with pytest.raises(ValueError, match="at least one entity"):
        HassLightController(_mock_client(), 0, entity_ids=[])


def test_multiple_entities_are_targeted_together_with_their_common_capabilities() -> None:
    client = _mock_client()
    client.get_state.side_effect = [
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
    controller = HassLightController(client, 0, entity_ids=["light.one", "light.two"])

    controller.change_light_state(LutMode.BRIGHTNESS, bri=100)
    client.trigger_service.assert_called_once_with(
        "light",
        "turn_on",
        entity_id=["light.one", "light.two"],
        brightness=100,
        transition=0,
    )
    info = controller.get_light_info()
    assert (info.min_mired, info.max_mired) == (200, 400)
    assert controller.get_effect_list() == ["shared"]


def _get_instance(client: MagicMock | None = None) -> HassLightController:
    return HassLightController(
        client or _mock_client(),
        0,
        entity_ids=["light.test"],
    )


def _mock_client() -> MagicMock:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_config.return_value = {}
    return client
