from unittest.mock import MagicMock, patch

import pytest
from homeassistant_api import Client, State
from measure.const import QUESTION_ENTITY_ID, QUESTION_MODEL_ID
from measure.controller.light.const import LutMode
from measure.controller.light.hass import HassLightController


def test_get_light_info() -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes={"min_color_temp_kelvin": 2202, "max_color_temp_kelvin": 6535},
    )
    with patch.multiple(
        "homeassistant_api.Client",
        get_state=MagicMock(return_value=mocked_state),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        light_info = hass_controller.get_light_info()
        assert light_info.get_min_mired() == 153
        assert light_info.get_max_mired() == 454


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


def _get_instance() -> HassLightController:
    with patch.multiple(
        "homeassistant_api.Client",
        get_config=MagicMock(return_value={}),
    ):
        return HassLightController("http://localhost:812", "abc", 0)
