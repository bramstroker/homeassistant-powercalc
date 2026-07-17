from unittest.mock import MagicMock

from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.errors import ApiConnectionError, ControllerError
from measure.controller.fan.hass import HassFanController
from measure.home_assistant import HomeAssistantManager
import pytest


def test_set_percentage() -> None:
    client = _mock_client()
    _get_instance(client).set_percentage(20)
    client.trigger_service.assert_called_once_with("fan", "set_percentage", entity_id="fan.test", percentage=20)


def test_set_percentage_error() -> None:
    client = _mock_client()
    client.trigger_service.side_effect = HomeassistantAPIError("Error")
    controller = _get_instance(client)
    with pytest.raises(ControllerError):
        controller.set_percentage(80)


def test_turn_off() -> None:
    client = _mock_client()
    _get_instance(client).turn_off()
    client.trigger_service.assert_called_once_with("fan", "turn_off", entity_id="fan.test")


def test_connection_validation() -> None:
    client = _mock_client()
    client.get_config.side_effect = HomeassistantAPIError("Error")
    with pytest.raises(ApiConnectionError):
        HassFanController(client)


def _get_instance(client: MagicMock | None = None) -> HassFanController:
    return HassFanController(client or _mock_client(), entity_id="fan.test")


def _mock_client() -> MagicMock:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_config.return_value = {}
    return client
