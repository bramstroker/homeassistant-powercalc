from unittest.mock import MagicMock

from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.errors import ApiConnectionError, ControllerError
from measure.controller.fan.hass import HassFanController
import pytest


def test_set_percentage(hass_client: MagicMock) -> None:
    _get_instance(hass_client).set_percentage(20)
    hass_client.trigger_service.assert_called_once_with("fan", "set_percentage", entity_id="fan.test", percentage=20)


def test_set_percentage_error(hass_client: MagicMock) -> None:
    hass_client.trigger_service.side_effect = HomeassistantAPIError("Error")
    controller = _get_instance(hass_client)
    with pytest.raises(ControllerError):
        controller.set_percentage(80)


def test_turn_off(hass_client: MagicMock) -> None:
    _get_instance(hass_client).turn_off()
    hass_client.trigger_service.assert_called_once_with("fan", "turn_off", entity_id="fan.test")


def test_turn_off_reports_service_failure(hass_client: MagicMock) -> None:
    error = HomeassistantAPIError("Service unavailable")
    hass_client.trigger_service.side_effect = error

    with pytest.raises(ControllerError, match="Failed to turn off fan") as raised:
        _get_instance(hass_client).turn_off()

    assert raised.value.__cause__ is error
    hass_client.trigger_service.assert_called_once_with("fan", "turn_off", entity_id="fan.test")


def test_connection_validation(hass_client: MagicMock) -> None:
    hass_client.get_config.side_effect = HomeassistantAPIError("Error")
    with pytest.raises(ApiConnectionError):
        HassFanController(hass_client)


def _get_instance(client: MagicMock) -> HassFanController:
    return HassFanController(client, entity_id="fan.test")
