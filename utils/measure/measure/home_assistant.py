from __future__ import annotations

from collections.abc import Callable
import contextlib
from threading import RLock
from types import TracebackType
from typing import Any, Self

from homeassistant_api import Entity, EntityRegistryEntry, Group, State, WebsocketClient

from measure.const import (
    HASS_DEVICE_REGISTRY_ID,
    HASS_DEVICE_REGISTRY_LIST,
    HASS_DEVICE_REGISTRY_MODEL,
    HASS_DEVICE_REGISTRY_MODEL_ID,
)


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

    def get_device_model(self, entity_id: str) -> str | None:
        """Return the preferred model identifier for an entity's device."""

        registry_entry = next((entry for entry in self.list_entity_registry() if entry.entity_id == entity_id), None)
        if registry_entry is None or registry_entry.device_id is None:
            return None
        device = next(
            (
                entry
                for entry in self.get_device_registry()
                if entry.get(HASS_DEVICE_REGISTRY_ID) == registry_entry.device_id
            ),
            None,
        )
        if device is None:
            return None
        model = device.get(HASS_DEVICE_REGISTRY_MODEL_ID) or device.get(HASS_DEVICE_REGISTRY_MODEL)
        return str(model) if model else None

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
    ) -> None:
        self.api_url = api_url
        self.token = token
        self._client_factory = client_factory or HomeAssistantWebsocketClient
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

    def get_config(self) -> dict[str, Any]:
        with self._lock:
            return self._connected_client().get_config()

    def get_entities(self) -> dict[str, Group]:
        with self._lock:
            return self._connected_client().get_entities()

    def get_state(
        self,
        *,
        entity_id: str | None = None,
        group_id: str | None = None,
        slug: str | None = None,
    ) -> State:
        with self._lock:
            return self._connected_client().get_state(entity_id=entity_id, group_id=group_id, slug=slug)

    def get_entity(
        self,
        group_id: str | None = None,
        slug: str | None = None,
        entity_id: str | None = None,
    ) -> Entity | None:
        with self._lock:
            return self._connected_client().get_entity(group_id=group_id, slug=slug, entity_id=entity_id)

    def trigger_service(self, domain: str, service: str, **service_data: Any) -> None:  # noqa: ANN401
        with self._lock:
            self._connected_client().trigger_service(domain, service, **service_data)

    def list_entity_registry(self) -> tuple[EntityRegistryEntry, ...]:
        with self._lock:
            return self._connected_client().list_entity_registry()

    def get_device_registry(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            return self._connected_client().get_device_registry()

    def get_device_model(self, entity_id: str) -> str | None:
        with self._lock:
            return self._connected_client().get_device_model(entity_id)

    def close(self) -> None:
        with self._lock:
            if self._client is None:
                return
            self._client.close()
            self._client = None
