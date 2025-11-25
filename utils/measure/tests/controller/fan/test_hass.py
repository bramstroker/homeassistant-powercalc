from unittest.mock import MagicMock, patch

from homeassistant_api import Client
from homeassistant_api.errors import HomeassistantAPIError
from measure.const import QUESTION_ENTITY_ID
from measure.controller.errors import ApiConnectionError, ControllerError
from measure.controller.fan.hass import HassFanController
import pytest


def test_set_percentage() -> None:
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "trigger_service",
        return_value=None,
    ) as mock_trigger_service:
        hass_controller.process_answers({QUESTION_ENTITY_ID: "fan.test"})
        hass_controller.set_percentage(20)

        mock_trigger_service.assert_called_once_with("fan", "set_percentage", entity_id="fan.test", percentage=20)


def test_set_percentage_error() -> None:
    hass_controller = _get_instance()
    with (
        patch.object(
            Client,
            "trigger_service",
            side_effect=HomeassistantAPIError("Error"),
        ),
        pytest.raises(ControllerError),
    ):
        hass_controller.set_percentage(80)


def test_turn_off() -> None:
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "trigger_service",
        return_value=None,
    ) as mock_trigger_service:
        hass_controller.process_answers({QUESTION_ENTITY_ID: "fan.test"})
        hass_controller.turn_off()

        mock_trigger_service.assert_called_once_with("fan", "turn_off", entity_id="fan.test")


def test_connection_validation() -> None:
    with (
        patch.object(
            Client,
            "get_config",
            side_effect=HomeassistantAPIError("Error"),
        ),
        pytest.raises(ApiConnectionError),
    ):
        HassFanController("http://localhost:812", "abc")


def test_get_questions() -> None:
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "get_entities",
        return_value={
            "fan": MagicMock(
                entities={
                    "fan.test1": MagicMock(entity_id="fan.test1"),
                    "fan.test2": MagicMock(entity_id="fan.test2"),
                },
            ),
        },
    ):
        questions = hass_controller.get_questions()
        assert len(questions) == 1
        assert questions[0].name == QUESTION_ENTITY_ID
        assert questions[0].choices == ["fan.test1", "fan.test2"]


def _get_instance() -> HassFanController:
    with patch.multiple(
        "homeassistant_api.Client",
        get_config=MagicMock(return_value={}),
    ):
        return HassFanController("http://localhost:812", "abc")
