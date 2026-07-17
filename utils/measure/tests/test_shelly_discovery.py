from __future__ import annotations

import asyncio
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock

from measure.ha_app.shelly_discovery import ShellyDiscoveryService
from measure.home_assistant import HomeAssistantDiscoveryClient, HomeAssistantDiscoveryError, HomeAssistantManager
import pytest
import requests


class FakeResponse:
    def __init__(self, data: object, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> object:
        if isinstance(self._data, ValueError):
            raise self._data
        return self._data


class FakeHomeAssistant:
    def __init__(self, services: Sequence[dict[str, object]] = (), error: Exception | None = None) -> None:
        self.services = tuple(services)
        self.error = error

    async def discover_zeroconf(self, collection_window: float = 2.0) -> tuple[dict[str, object], ...]:
        assert collection_window == pytest.approx(2.0)
        if self.error:
            raise self.error
        return self.services


def service(name: str, service_type: str, addresses: list[str]) -> dict[str, object]:
    return {"name": name, "type": service_type, "ip_addresses": addresses, "port": 80, "properties": {}}


def response_map(responses: dict[str, FakeResponse | Exception]) -> MagicMock:
    def get(url: str, *, timeout: int, allow_redirects: bool) -> FakeResponse:
        assert timeout == 2
        assert allow_redirects is False
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    return MagicMock(side_effect=get)


def test_home_assistant_discovery_client_collects_add_events_until_timeout() -> None:
    client = MagicMock(spec=HomeAssistantDiscoveryClient)
    client.send = AsyncMock(return_value=7)
    client._async_recv = AsyncMock(  # noqa: SLF001
        side_effect=(
            {"id": 7, "type": "result", "success": True, "result": None},
            {"id": 7, "type": "event", "event": {"add": [{"name": "shelly-one"}], "remove": []}},
            TimeoutError,
        ),
    )

    result = asyncio.run(HomeAssistantDiscoveryClient.discover_zeroconf(client, 0.1))

    assert result == ({"name": "shelly-one"},)
    client.send.assert_awaited_once_with("zeroconf/subscribe_discovery")


def test_home_assistant_discovery_client_reports_rejected_subscription() -> None:
    client = MagicMock(spec=HomeAssistantDiscoveryClient)
    client.send = AsyncMock(return_value=3)
    client._async_recv = AsyncMock(  # noqa: SLF001
        return_value={"id": 3, "type": "result", "success": False, "error": {"message": "Unknown command"}},
    )

    coroutine = HomeAssistantDiscoveryClient.discover_zeroconf(client, 0.1)
    with pytest.raises(HomeAssistantDiscoveryError, match="Unknown command"):
        asyncio.run(coroutine)


def test_manager_uses_an_ephemeral_discovery_client() -> None:
    client = MagicMock(spec=HomeAssistantDiscoveryClient)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.discover_zeroconf = AsyncMock(return_value=({"name": "shelly-one"},))
    factory = MagicMock(return_value=client)
    manager = HomeAssistantManager("ws://127.0.0.1/api/websocket", "token", discovery_client_factory=factory)

    result = asyncio.run(manager.discover_zeroconf(0.25))

    assert result == ({"name": "shelly-one"},)
    factory.assert_called_once_with("ws://127.0.0.1/api/websocket", "token")
    client.discover_zeroconf.assert_awaited_once_with(0.25)
    client.__aexit__.assert_awaited_once()


def test_discovers_supported_gen1_and_gen2_devices_and_filters_other_http_services() -> None:
    home_assistant = FakeHomeAssistant(
        (
            service("shellyplug-s-abc._http._tcp.local.", "_http._tcp.local.", ["192.168.1.10"]),
            service("Shelly Plus Plug", "_shelly._tcp.local.", ["192.168.1.11"]),
            service("printer", "_http._tcp.local.", ["192.168.1.12"]),
        ),
    )
    http_get = response_map(
        {
            "http://192.168.1.10/shelly": FakeResponse({"type": "SHPLG-S", "mac": "AABBCC", "gen": 1}),
            "http://192.168.1.10/status": FakeResponse({"meters": [{"power": 1.2}]}),
            "http://192.168.1.11/shelly": FakeResponse(
                {"id": "shellyplusplugs-123", "name": "Desk plug", "model": "SNPL-00112EU", "gen": 2},
            ),
            "http://192.168.1.11/rpc/Shelly.GetStatus": FakeResponse({"switch:0": {"apower": 2.4}}),
        },
    )

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    assert result.available is True
    assert [(device.name, device.model, device.generation, device.supported) for device in result.devices] == [
        ("Desk plug", "SNPL-00112EU", 2, True),
        ("shellyplug-s-abc", "SHPLG-S", 1, True),
    ]
    assert "http://192.168.1.12/shelly" not in {call.args[0] for call in http_get.call_args_list}


def test_lists_authenticated_unsupported_and_ipv6_only_devices_with_reasons() -> None:
    home_assistant = FakeHomeAssistant(
        (
            service("shelly-auth", "_shelly._tcp.local.", ["192.168.1.20"]),
            service("shelly-no-meter", "_shelly._tcp.local.", ["192.168.1.21"]),
            service("shelly-ipv6", "_shelly._tcp.local.", ["fe80::1"]),
        ),
    )
    http_get = response_map(
        {
            "http://192.168.1.20/shelly": FakeResponse(
                {"id": "shelly-auth", "model": "S3PL-00112EU", "gen": 3, "auth_en": True},
            ),
            "http://192.168.1.21/shelly": FakeResponse({"id": "shelly-no-meter", "model": "S3SN-0U12A", "gen": 3}),
            "http://192.168.1.21/rpc/Shelly.GetStatus": FakeResponse({"wifi": {"sta_ip": "192.168.1.21"}}),
        },
    )

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    devices = {device.id: device for device in result.devices}
    assert devices["shelly-auth"].auth_required is True
    assert "Authentication" in str(devices["shelly-auth"].reason)
    assert devices["shelly-no-meter"].supported is False
    assert "power measurement component" in str(devices["shelly-no-meter"].reason)
    assert "IPv6" in str(devices["shelly-ipv6"].reason)


def test_rejects_unsafe_addresses_without_probing() -> None:
    http_get = MagicMock()
    home_assistant = FakeHomeAssistant((service("shelly-loopback", "_shelly._tcp.local.", ["127.0.0.1"]),))

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    assert result.devices[0].supported is False
    assert "private LAN" in str(result.devices[0].reason)
    http_get.assert_not_called()


def test_discovery_failure_keeps_manual_configuration_available() -> None:
    home_assistant = FakeHomeAssistant(error=HomeAssistantDiscoveryError("Unknown command"))

    result = asyncio.run(ShellyDiscoveryService(home_assistant).discover())  # type: ignore[arg-type]

    assert result.available is False
    assert result.devices == []
    assert "manually" in str(result.message)


def test_duplicate_advertisements_are_probed_once() -> None:
    duplicate = service("shelly-duplicate", "_shelly._tcp.local.", ["192.168.1.30"])
    home_assistant = FakeHomeAssistant((duplicate, duplicate | {"type": "_http._tcp.local."}))
    http_get = response_map(
        {
            "http://192.168.1.30/shelly": FakeResponse({"id": "shelly-duplicate", "gen": 2}),
            "http://192.168.1.30/rpc/Shelly.GetStatus": FakeResponse({"switch:0": {"apower": 1.0}}),
        },
    )

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    assert len(result.devices) == 1
    assert http_get.call_count == 2


def test_unreachable_device_is_visible_but_disabled() -> None:
    home_assistant = FakeHomeAssistant((service("shelly-offline", "_shelly._tcp.local.", ["192.168.1.40"]),))
    http_get = response_map({"http://192.168.1.40/shelly": requests.ConnectionError("offline")})

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    assert result.devices[0].supported is False
    assert "could not be reached" in str(result.devices[0].reason)


def test_discovers_gen3_pm1_component() -> None:
    home_assistant = FakeHomeAssistant((service("shelly-pm-mini", "_shelly._tcp.local.", ["192.168.1.50"]),))
    http_get = response_map(
        {
            "http://192.168.1.50/shelly": FakeResponse(
                {"id": "shellypmmini-123", "name": "Fuse box", "model": "S3PM-001PCEU16", "gen": 3},
            ),
            "http://192.168.1.50/rpc/Shelly.GetStatus": FakeResponse({"pm1:0": {"apower": 4.2, "voltage": 229.8}}),
        },
    )

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    assert len(result.devices) == 1
    assert result.devices[0].generation == 3
    assert result.devices[0].model == "S3PM-001PCEU16"
    assert result.devices[0].supported is True


def test_lists_multichannel_device_as_unsupported() -> None:
    home_assistant = FakeHomeAssistant((service("shelly-2pm", "_shelly._tcp.local.", ["192.168.1.51"]),))
    http_get = response_map(
        {
            "http://192.168.1.51/shelly": FakeResponse({"id": "shelly-2pm", "gen": 3}),
            "http://192.168.1.51/rpc/Shelly.GetStatus": FakeResponse(
                {"switch:0": {"apower": 1.0}, "switch:1": {"apower": 2.0}},
            ),
        },
    )

    result = asyncio.run(ShellyDiscoveryService(home_assistant, http_get=http_get).discover())  # type: ignore[arg-type]

    assert result.devices[0].supported is False
    assert "Multiple power measurement components" in str(result.devices[0].reason)
