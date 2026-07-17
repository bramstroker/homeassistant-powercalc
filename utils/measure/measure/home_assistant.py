from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
from threading import RLock
from types import TracebackType
from typing import Any, Self
import urllib.parse

from homeassistant_api import AsyncWebsocketClient, Entity, EntityRegistryEntry, Group, State, WebsocketClient
from homeassistant_api.errors import WebsocketError

from measure.const import HASS_DEVICE_REGISTRY_LIST, HASS_ZEROCONF_SUBSCRIBE_DISCOVERY


class HomeAssistantDiscoveryError(RuntimeError):
    """Raised when Home Assistant rejects a discovery subscription."""


def normalize_hass_url(url: str) -> str:
    """Normalize a Home Assistant URL to its WebSocket API endpoint.

    Older measure installations configured the REST endpoint
    (e.g. ``http://ha.lan:8123/api``); the WebSocket API lives at
    ``/api/websocket`` and uses the ``ws``/``wss`` scheme.
    """

    parsed = urllib.parse.urlparse(url)
    scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme, parsed.scheme)
    path = parsed.path.rstrip("/")
    if not path:
        path = "/api"
    if not path.endswith("/websocket"):
        path += "/websocket"
    return urllib.parse.urlunparse(parsed._replace(scheme=scheme, path=path))


def _validate_subscription_response(response: dict[str, Any], subscription_id: object) -> None:
    if response.get("id") != subscription_id or response.get("type") != "result":
        raise HomeAssistantDiscoveryError("Unexpected Home Assistant discovery response")
    if response.get("success") is not True:
        error = response.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        raise HomeAssistantDiscoveryError(str(message or "Home Assistant discovery is unavailable"))


def _added_services(event_response: dict[str, Any], subscription_id: object) -> list[dict[str, object]]:
    if event_response.get("id") != subscription_id or event_response.get("type") != "event":
        return []
    event = event_response.get("event")
    if not isinstance(event, dict):
        return []
    added = event.get("add")
    if not isinstance(added, list):
        return []
    return [service for service in added if isinstance(service, dict)]


class HomeAssistantDiscoveryClient(AsyncWebsocketClient):
    """Read raw Home Assistant Zeroconf subscription events."""

    async def discover_zeroconf(self, collection_window: float) -> tuple[dict[str, object], ...]:
        subscription_id = await self.send(HASS_ZEROCONF_SUBSCRIBE_DISCOVERY)
        _validate_subscription_response(await self._async_recv(), subscription_id)

        services: list[dict[str, object]] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + collection_window
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                event_response = await asyncio.wait_for(self._async_recv(), timeout=remaining)
            except TimeoutError:
                break
            services.extend(_added_services(event_response, subscription_id))
        return tuple(services)


@dataclass(frozen=True)
class HomeAssistantEntityData:
    """Raw live entity and registry data captured under one client lock."""

    entities: dict[str, Group]
    entity_registry: tuple[EntityRegistryEntry, ...]
    device_registry: tuple[dict[str, object], ...]


class HomeAssistantWebsocketClient(WebsocketClient):
    """WebSocket client with explicit reusable connection management."""

    def __init__(self, api_url: str, token: str) -> None:
        super().__init__(api_url, token)
        self._connected = False

    def connect(self) -> Self:
        if not self._connected:
            super().__enter__()
            self._connected = True
        return self

    def __enter__(self) -> Self:
        return self.connect()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connected:
            super().__exit__(exc_type, exc_value, traceback)
            self._connected = False

    def close(self) -> None:
        self.__exit__(None, None, None)

    def get_device_registry(self) -> tuple[dict[str, object], ...]:
        """Return Home Assistant device registry entries."""

        return tuple(self.recv_result_list(self.send(HASS_DEVICE_REGISTRY_LIST)))

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()


class HomeAssistantManager:
    """Own and serialize access to one Home Assistant client per lifecycle."""

    def __init__(
        self,
        api_url: str,
        token: str,
        *,
        client_factory: Callable[[str, str], HomeAssistantWebsocketClient] | None = None,
        discovery_client_factory: Callable[[str, str], HomeAssistantDiscoveryClient] | None = None,
    ) -> None:
        self.api_url = normalize_hass_url(api_url)
        self.token = token
        self._client_factory = client_factory or HomeAssistantWebsocketClient
        self._discovery_client_factory = discovery_client_factory or HomeAssistantDiscoveryClient
        self._client: HomeAssistantWebsocketClient | None = None
        self._lock = RLock()

    def _connected_client(self) -> HomeAssistantWebsocketClient:
        if self._client is None:
            client = self._client_factory(self.api_url, self.token)
            try:
                client.connect()
            except Exception:
                with contextlib.suppress(Exception):
                    client.close()
                raise
            self._client = client
        return self._client

    @staticmethod
    def _is_connection_error(error: BaseException) -> bool:
        pending = [error]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            if isinstance(current, OSError | EOFError | WebsocketError):
                return True
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
        return False

    def _discard_client(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    def _execute[T](
        self,
        operation: Callable[[HomeAssistantWebsocketClient], T],
        *,
        retry_on_disconnect: bool = True,
    ) -> T:
        with self._lock:
            client = self._connected_client()
            try:
                return operation(client)
            except Exception as error:
                if not self._is_connection_error(error):
                    raise
                self._discard_client()
                if not retry_on_disconnect:
                    raise

            try:
                return operation(self._connected_client())
            except Exception as error:
                if self._is_connection_error(error):
                    self._discard_client()
                raise

    def get_config(self) -> dict[str, Any]:
        return self._execute(lambda client: client.get_config())

    def get_entities(self) -> dict[str, Group]:
        return self._execute(lambda client: client.get_entities())

    def get_state(
        self,
        *,
        entity_id: str | None = None,
        group_id: str | None = None,
        slug: str | None = None,
    ) -> State:
        return self._execute(lambda client: client.get_state(entity_id=entity_id, group_id=group_id, slug=slug))

    def get_entity(
        self,
        group_id: str | None = None,
        slug: str | None = None,
        entity_id: str | None = None,
    ) -> Entity | None:
        return self._execute(lambda client: client.get_entity(group_id=group_id, slug=slug, entity_id=entity_id))

    def trigger_service(self, domain: str, service: str, **service_data: Any) -> None:  # noqa: ANN401
        self._execute(
            lambda client: client.trigger_service(domain, service, **service_data),
            retry_on_disconnect=False,
        )

    def list_entity_registry(self) -> tuple[EntityRegistryEntry, ...]:
        return self._execute(lambda client: client.list_entity_registry())

    def get_device_registry(self) -> tuple[dict[str, object], ...]:
        return self._execute(lambda client: client.get_device_registry())

    def get_entity_data(self) -> HomeAssistantEntityData:
        """Load fresh entity and registry data as one consistency unit."""

        return self._execute(
            lambda client: HomeAssistantEntityData(
                entities=client.get_entities(),
                entity_registry=tuple(client.list_entity_registry()),
                device_registry=tuple(client.get_device_registry()),
            ),
        )

    async def discover_zeroconf(self, collection_window: float = 2.0) -> tuple[dict[str, object], ...]:
        """Collect the current Home Assistant Zeroconf discovery results."""

        async with self._discovery_client_factory(self.api_url, self.token) as client:
            return await client.discover_zeroconf(collection_window)

    def close(self) -> None:
        with self._lock:
            self._discard_client()
