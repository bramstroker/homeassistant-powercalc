from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from unittest.mock import MagicMock

from homeassistant_api.errors import WebsocketError
from measure.const import HASS_ENTITY_REGISTRY_LIST
from measure.home_assistant import HomeAssistantManager, HomeAssistantWebsocketClient, normalize_hass_url
import pytest
from urllib3.exceptions import ProtocolError


def test_client_uses_canonical_websocket_url() -> None:
    client = HomeAssistantWebsocketClient("ws://127.0.0.1:8123/api/websocket", "token")

    assert client.api_url == "ws://127.0.0.1:8123/api/websocket"


def test_client_sends_non_blocking_websocket_ping() -> None:
    class PingWebSocket:
        def __init__(self) -> None:
            self.ping_calls = 0

        def ping(self) -> None:
            self.ping_calls += 1

    client = HomeAssistantWebsocketClient("ws://127.0.0.1:8123/api/websocket", "token")
    websocket = PingWebSocket()
    client._ws = websocket  # type: ignore[assignment]  # noqa: SLF001 - exercise the protocol adapter

    client.send_ping()

    assert websocket.ping_calls == 1


def test_client_rejects_websocket_implementation_without_protocol_ping() -> None:
    client = HomeAssistantWebsocketClient("ws://127.0.0.1:8123/api/websocket", "token")
    client._ws = object()  # type: ignore[assignment]  # noqa: SLF001 - simulate an unsupported extension

    with pytest.raises(WebsocketError, match="does not support protocol pings"):
        client.send_ping()


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
    "url, expected",
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


def test_manager_fires_home_assistant_event() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = HomeAssistantManager(
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=MagicMock(return_value=client),
    )

    manager.fire_event("powercalc_measure_status", state="idle")

    client.fire_event.assert_called_once_with("powercalc_measure_status", state="idle")


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


def test_manager_replays_service_call_on_a_fresh_client_after_disconnect() -> None:
    disconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    disconnected_client.trigger_service.side_effect = OSError("stream closed error")
    reconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    client_factory = MagicMock(side_effect=(disconnected_client, reconnected_client))
    manager = HomeAssistantManager(
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    manager.trigger_service("media_player", "turn_off", entity_id="media_player.test")

    disconnected_client.close.assert_called_once_with()
    reconnected_client.trigger_service.assert_called_once_with(
        "media_player",
        "turn_off",
        entity_id="media_player.test",
    )


def test_manager_reraises_service_call_failure_when_reconnect_also_fails() -> None:
    disconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    first_error = ProtocolError("stream closed error")
    first_error.__cause__ = BrokenPipeError("broken pipe")
    disconnected_client.trigger_service.side_effect = first_error
    reconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    second_error = ProtocolError("stream closed again")
    second_error.__cause__ = BrokenPipeError("broken pipe")
    reconnected_client.trigger_service.side_effect = second_error
    client_factory = MagicMock(side_effect=(disconnected_client, reconnected_client))
    manager = HomeAssistantManager(
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(WebsocketError, match="stream closed again") as exc_info:
        manager.trigger_service("media_player", "turn_off", entity_id="media_player.test")

    assert exc_info.value.__cause__ is second_error
    disconnected_client.close.assert_called_once_with()
    reconnected_client.close.assert_called_once_with()


def test_manager_does_not_replay_service_call_when_retry_is_disabled() -> None:
    disconnected_client = MagicMock(spec=HomeAssistantWebsocketClient)
    error = ProtocolError("stream closed error")
    error.__cause__ = BrokenPipeError("broken pipe")
    disconnected_client.trigger_service.side_effect = error
    client_factory = MagicMock(return_value=disconnected_client)
    manager = HomeAssistantManager(
        "ws://127.0.0.1:8123/api/websocket",
        "token",
        client_factory=client_factory,
    )

    with pytest.raises(WebsocketError, match="stream closed error") as exc_info:
        manager.trigger_service(
            "media_player",
            "play_media",
            retry_on_disconnect=False,
            entity_id="media_player.test",
        )

    assert exc_info.value.__cause__ is error
    client_factory.assert_called_once_with("ws://127.0.0.1:8123/api/websocket", "token")
    disconnected_client.close.assert_called_once_with()


def _keepalive_manager(client: MagicMock, *, keepalive_interval: float = 20.0) -> HomeAssistantManager:
    return HomeAssistantManager(
        "ws://supervisor/core/websocket",
        "token",
        client_factory=MagicMock(return_value=client),
        keepalive_interval=keepalive_interval,
    )


def test_keepalive_pings_a_connection_that_went_quiet() -> None:
    """Long effect measurements leave the socket unread, so the proxy drops it. See #4543."""

    client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = _keepalive_manager(client)
    manager.get_config()
    manager._last_activity -= 60  # noqa: SLF001 - simulate a measurement that took a minute

    manager.send_keepalive()

    client.send_ping.assert_called_once_with()
    client.ping_latency.assert_not_called()


def test_keepalive_stays_quiet_while_measurements_keep_the_socket_busy() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = _keepalive_manager(client)
    manager.get_config()

    manager.send_keepalive()

    client.send_ping.assert_not_called()


def test_keepalive_stays_quiet_after_shutdown_starts() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = _keepalive_manager(client)
    manager.get_config()
    manager._last_activity -= 60  # noqa: SLF001
    manager._keepalive_stop.set()  # noqa: SLF001 - simulate close while the pinger waits for the client lock

    manager.send_keepalive()

    client.send_ping.assert_not_called()


def test_keepalive_does_not_open_a_connection_of_its_own() -> None:
    client_factory = MagicMock()
    manager = HomeAssistantManager("ws://supervisor/core/websocket", "token", client_factory=client_factory)

    manager.send_keepalive()

    client_factory.assert_not_called()


def test_keepalive_discards_the_client_when_the_ping_fails() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    client.send_ping.side_effect = ProtocolError("stream closed error")
    manager = _keepalive_manager(client)
    manager.get_config()
    manager._last_activity -= 60  # noqa: SLF001

    manager.send_keepalive()

    client.close.assert_called_once_with()


def test_manager_can_restart_keepalive_after_close() -> None:
    first_client = MagicMock(spec=HomeAssistantWebsocketClient)
    second_client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = HomeAssistantManager(
        "ws://supervisor/core/websocket",
        "token",
        client_factory=MagicMock(side_effect=(first_client, second_client)),
        keepalive_interval=0.02,
    )
    manager.get_config()
    first_thread = manager._keepalive_thread  # noqa: SLF001

    manager.close()
    manager.get_config()
    second_thread = manager._keepalive_thread  # noqa: SLF001

    assert first_thread is not None
    assert not first_thread.is_alive()
    assert second_thread is not None
    assert second_thread is not first_thread
    assert second_thread.is_alive()
    manager.close()


def test_keepalive_thread_pings_until_the_manager_is_closed() -> None:
    client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = _keepalive_manager(client, keepalive_interval=0.02)
    manager.get_config()

    for _ in range(100):
        if client.send_ping.call_count:
            break
        sleep(0.01)
    manager.close()
    pings_at_close = client.send_ping.call_count

    assert pings_at_close > 0
    sleep(0.1)
    assert client.send_ping.call_count == pings_at_close


def test_keepalive_interval_of_zero_starts_no_background_thread() -> None:
    """Lets the CLI and tests opt out of a pinger they have no use for."""

    client = MagicMock(spec=HomeAssistantWebsocketClient)
    manager = _keepalive_manager(client, keepalive_interval=0)
    manager.get_config()

    assert manager._keepalive_thread is None  # noqa: SLF001
    client.send_ping.assert_not_called()
