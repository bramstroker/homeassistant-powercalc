from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from unittest.mock import MagicMock

from measure.const import HASS_ENTITY_REGISTRY_LIST
from measure.home_assistant import HomeAssistantManager, HomeAssistantWebsocketClient, normalize_hass_url
import pytest


def test_client_uses_canonical_websocket_url() -> None:
    client = HomeAssistantWebsocketClient("ws://127.0.0.1:8123/api/websocket", "token")

    assert client.api_url == "ws://127.0.0.1:8123/api/websocket"


def _entity_registry_entry(*, entity_id: str, unique_id: object) -> dict[str, object]:
    return {
        "created_at": "2026-07-18T12:00:00+00:00",
        "entity_id": entity_id,
        "has_entity_name": True,
        "id": entity_id,
        "modified_at": "2026-07-18T12:00:00+00:00",
        "platform": "test",
        "unique_id": unique_id,
    }


def test_entity_registry_normalizes_numeric_unique_id() -> None:
    client = HomeAssistantWebsocketClient("ws://127.0.0.1:8123/api/websocket", "token")
    client.send = MagicMock(return_value=42)  # type: ignore[method-assign]
    client.recv_result_list = MagicMock(  # type: ignore[method-assign]
        return_value=[_entity_registry_entry(entity_id="sensor.battery", unique_id=609369805)],
    )

    entries = client.list_entity_registry()

    assert entries[0].unique_id == "609369805"
    client.send.assert_called_once_with(HASS_ENTITY_REGISTRY_LIST)
    client.recv_result_list.assert_called_once_with(42)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://ha.lan:8123/api", "ws://ha.lan:8123/api/websocket"),
        ("https://ha.lan:8123/api/", "wss://ha.lan:8123/api/websocket"),
        ("http://ha.lan:8123", "ws://ha.lan:8123/api/websocket"),
        ("https://my.duckdns.org", "wss://my.duckdns.org/api/websocket"),
        ("ws://127.0.0.1:8123/api/websocket", "ws://127.0.0.1:8123/api/websocket"),
        ("wss://ha.lan:8123/api/websocket", "wss://ha.lan:8123/api/websocket"),
        ("ws://supervisor/core/websocket", "ws://supervisor/core/websocket"),
    ],
)
def test_normalize_hass_url(url: str, expected: str) -> None:
    assert normalize_hass_url(url) == expected


def test_manager_normalizes_legacy_rest_url() -> None:
    client_factory = MagicMock(return_value=MagicMock(spec=HomeAssistantWebsocketClient))
    manager = HomeAssistantManager("http://ha.lan:8123/api", "token", client_factory=client_factory)

    assert manager.api_url == "ws://ha.lan:8123/api/websocket"

    manager.get_config()
    client_factory.assert_called_once_with("ws://ha.lan:8123/api/websocket", "token")


def test_manager_reuses_one_client_for_its_lifecycle() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    client.get_config.return_value = {"location_name": "Home"}
    client_factory = MagicMock(return_value=client)
    manager = HomeAssistantManager(
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    assert manager.get_config() == {"location_name": "Home"}
    assert manager.get_config() == {"location_name": "Home"}

    client_factory.assert_called_once_with("ws://127.0.0.1:8123/api/websocket", "token")
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
        "ws://127.0.0.1:8123/api/websocket",
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
        "ws://127.0.0.1:8123/api/websocket",
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
        "ws://127.0.0.1:8123/api/websocket",
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
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(ValueError, match="invalid entity response"):
        manager.get_entities()

    client_factory.assert_called_once_with("ws://127.0.0.1:8123/api/websocket", "token")
    client.close.assert_not_called()


def test_manager_does_not_retry_service_call_after_disconnect() -> None:
    disconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    disconnected_client.trigger_service.side_effect = OSError("stream closed error")
    reconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    reconnected_client.get_config.return_value = {"location_name": "Home"}
    client_factory = MagicMock(side_effect=(disconnected_client, reconnected_client))
    manager = HomeAssistantManager(
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(OSError, match="stream closed error"):
        manager.trigger_service("media_player", "turn_off", entity_id="media_player.test")

    assert manager.get_config() == {"location_name": "Home"}
    disconnected_client.close.assert_called_once_with()
    reconnected_client.trigger_service.assert_not_called()
