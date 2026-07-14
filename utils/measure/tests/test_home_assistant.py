from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from measure.home_assistant import HomeAssistantManager, HomeAssistantWebsocketClient
import pytest


def test_client_uses_canonical_websocket_url() -> None:
    client = HomeAssistantWebsocketClient("ws://homeassistant.local:8123/api/websocket", "token")

    assert client.api_url == "ws://homeassistant.local:8123/api/websocket"


def test_device_model_prefers_model_id_and_falls_back_to_model() -> None:
    client = HomeAssistantWebsocketClient("ws://homeassistant.local:8123/api/websocket", "token")
    registry = (
        SimpleNamespace(entity_id="light.preferred", device_id="preferred-device"),
        SimpleNamespace(entity_id="light.fallback", device_id="fallback-device"),
    )
    devices = (
        {"id": "preferred-device", "model_id": "LWA017", "model": "Hue White Ambiance"},
        {"id": "fallback-device", "model_id": None, "model": "Hue White"},
    )

    with (
        patch.object(client, "list_entity_registry", return_value=registry),
        patch.object(client, "get_device_registry", return_value=devices),
    ):
        assert client.get_device_model("light.preferred") == "LWA017"
        assert client.get_device_model("light.fallback") == "Hue White"


def test_manager_reuses_one_client_for_its_lifecycle() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    client.get_config.return_value = {"location_name": "Home"}
    client_factory = MagicMock(return_value=client)
    manager = HomeAssistantManager(
        "ws://homeassistant.local:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    assert manager.get_config() == {"location_name": "Home"}
    assert manager.get_config() == {"location_name": "Home"}

    client_factory.assert_called_once_with("ws://homeassistant.local:8123/api/websocket", "token")
    client.connect.assert_called_once_with()

    manager.close()
    manager.close()
    client.close.assert_called_once_with()


def test_manager_serializes_access_to_shared_websocket() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    active_calls = 0
    maximum_active_calls = 0
    counter_lock = Lock()

    def get_config() -> dict[str, str]:
        nonlocal active_calls, maximum_active_calls
        with counter_lock:
            active_calls += 1
            maximum_active_calls = max(maximum_active_calls, active_calls)
        sleep(0.01)
        with counter_lock:
            active_calls -= 1
        return {"location_name": "Home"}

    client.get_config.side_effect = get_config
    manager = HomeAssistantManager(
        "ws://homeassistant.local:8123/api/websocket",
        "token",
        client_factory=MagicMock(return_value=client),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: manager.get_config(), range(2)))

    assert results == ({"location_name": "Home"}, {"location_name": "Home"})
    assert maximum_active_calls == 1


def test_manager_discards_client_when_connection_fails() -> None:
    failed_client = MagicMock(spec=HomeAssistantWebsocketClient)
    failed_client.connect.side_effect = OSError("connection failed")
    connected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    connected_client.get_config.return_value = {"location_name": "Home"}
    client_factory = MagicMock(side_effect=(failed_client, connected_client))
    manager = HomeAssistantManager(
        "ws://homeassistant.local:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(OSError, match="connection failed"):
        manager.get_config()

    assert manager.get_config() == {"location_name": "Home"}
    assert client_factory.call_count == 2
    failed_client.close.assert_called_once_with()


def test_manager_reconnects_once_when_read_fails_on_closed_websocket() -> None:
    disconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)

    def fail_with_websocket_cleanup_error() -> None:
        try:
            try:
                raise OSError("stream closed error")
            except OSError as error:
                raise RuntimeError("connection broken") from error
        except RuntimeError:
            raise AssertionError from None

    disconnected_client.get_entities.side_effect = fail_with_websocket_cleanup_error
    disconnected_client.close.side_effect = AssertionError
    reconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    reconnected_client.get_entities.return_value = {"media_player": MagicMock()}
    client_factory = MagicMock(side_effect=(disconnected_client, reconnected_client))
    manager = HomeAssistantManager(
        "ws://homeassistant.local:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    assert manager.get_entities() == {"media_player": reconnected_client.get_entities.return_value["media_player"]}
    assert client_factory.call_count == 2
    disconnected_client.close.assert_called_once_with()
    reconnected_client.get_entities.assert_called_once_with()


def test_manager_does_not_retry_non_connection_errors() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    client.get_entities.side_effect = ValueError("invalid entity response")
    client_factory = MagicMock(return_value=client)
    manager = HomeAssistantManager(
        "ws://homeassistant.local:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(ValueError, match="invalid entity response"):
        manager.get_entities()

    client_factory.assert_called_once_with("ws://homeassistant.local:8123/api/websocket", "token")
    client.close.assert_not_called()


def test_manager_does_not_retry_service_call_after_disconnect() -> None:
    disconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    disconnected_client.trigger_service.side_effect = OSError("stream closed error")
    reconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    reconnected_client.get_config.return_value = {"location_name": "Home"}
    client_factory = MagicMock(side_effect=(disconnected_client, reconnected_client))
    manager = HomeAssistantManager(
        "ws://homeassistant.local:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(OSError, match="stream closed error"):
        manager.trigger_service("media_player", "turn_off", entity_id="media_player.test")

    assert manager.get_config() == {"location_name": "Home"}
    disconnected_client.close.assert_called_once_with()
    reconnected_client.trigger_service.assert_not_called()
