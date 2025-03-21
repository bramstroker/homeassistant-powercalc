from unittest.mock import MagicMock, patch

import pytest
from homeassistant_api import Client, HomeassistantAPIError, State
from measure.const import QUESTION_ENTITY_ID, QUESTION_MODEL_ID
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.errors import ApiConnectionError
from measure.controller.light.hass import HassLightController


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
    with patch.multiple(
        "homeassistant_api.Client",
        get_state=MagicMock(return_value=mocked_state),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        light_info = hass_controller.get_light_info()
        assert light_info.get_min_mired() == min_mired
        assert light_info.get_max_mired() == max_mired


def test_effect_list() -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes={"effect_list": ["A", "B", "C"]},
    )
    with patch.multiple(
        "homeassistant_api.Client",
        get_state=MagicMock(return_value=mocked_state),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        assert hass_controller.get_effect_list() == ["A", "B", "C"]


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
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "trigger_service",
        return_value=None,
    ) as mock_trigger_service:
        hass_controller.process_answers({QUESTION_ENTITY_ID: "light.test", QUESTION_MODEL_ID: "test"})
        hass_controller.change_light_state(mode, on=True, **call_kwargs)

        mock_trigger_service.assert_called_once_with("light", "turn_on", entity_id="light.test", **trigger_service_body)


def test_turn_off() -> None:
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "trigger_service",
        return_value=None,
    ) as mock_trigger_service:
        hass_controller.process_answers({QUESTION_ENTITY_ID: "light.test", QUESTION_MODEL_ID: "test"})
        hass_controller.change_light_state(LutMode.BRIGHTNESS, on=False)

        mock_trigger_service.assert_called_once_with("light", "turn_off", entity_id="light.test")


def test_change_light_state_error() -> None:
    hass_controller = _get_instance()
    with (
        patch.object(
            Client,
            "trigger_service",
            side_effect=HomeassistantAPIError("Error"),
        ),
        pytest.raises(ApiConnectionError),
    ):
        hass_controller.change_light_state(LutMode.BRIGHTNESS, on=True, bri=100)


def test_connection_validation() -> None:
    with (
        patch.object(
            Client,
            "get_config",
            side_effect=HomeassistantAPIError("Error"),
        ),
        pytest.raises(ApiConnectionError),
    ):
        HassLightController("http://localhost:812", "abc", 0)


def test_get_questions() -> None:
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "get_entities",
        return_value={
            "light": MagicMock(
                entities={
                    "light.test1": MagicMock(entity_id="light.test1"),
                    "light.test2": MagicMock(entity_id="light.test2"),
                },
            ),
        },
    ):
        questions = hass_controller.get_questions()
        assert len(questions) == 2
        assert questions[0].name == QUESTION_ENTITY_ID
        assert questions[1].name == QUESTION_MODEL_ID
        assert questions[0].choices == ["light.test1", "light.test2"]


def _get_instance() -> HassLightController:
    with patch.multiple(
        "homeassistant_api.Client",
        get_config=MagicMock(return_value={}),
    ):
        return HassLightController("http://localhost:812", "abc", 0)
