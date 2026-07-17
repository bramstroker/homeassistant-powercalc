from __future__ import annotations

from homeassistant_api import State

from measure.controller.errors import ApiConnectionError, ControllerError
from measure.home_assistant import HomeAssistantManager


class HassControllerBase:
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        *,
        entity_id: str | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.client = home_assistant
        try:
            self.client.get_config()
        except Exception as e:
            raise ApiConnectionError(f"Failed to connect to HA API: {e}") from e

    def get_entity_state(self) -> State:
        entity = self.client.get_entity(entity_id=self.entity_id)
        if not entity:
            raise ControllerError(f"Entity {self.entity_id} not found")
        return entity.state
