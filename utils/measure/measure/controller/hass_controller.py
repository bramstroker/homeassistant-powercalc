from typing import Any

from homeassistant_api import Client, State
from homeassistant_api.errors import HomeassistantAPIError

from measure.const import QUESTION_ENTITY_ID
from measure.controller.errors import ApiConnectionError, ControllerError


class HassControllerBase:
    def __init__(self, api_url: str, token: str) -> None:
        self.entity_id: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
            self.client.get_config()
        except HomeassistantAPIError as e:
            raise ApiConnectionError(f"Failed to connect to HA API: {e}") from e

    def process_answers(self, answers: dict[str, Any]) -> None:
        self.entity_id = answers[QUESTION_ENTITY_ID]

    def get_domain_entity_list(self, domain: str) -> list:
        entities = self.client.get_entities()
        if domain not in entities:
            return []
        found_entities = entities[domain].entities.values()
        return sorted([entity.entity_id for entity in found_entities])

    def get_entity_state(self) -> State:
        entity = self.client.get_entity(entity_id=self.entity_id)
        if not entity:
            raise ControllerError(f"Entity {self.entity_id} not found")
        return entity.state
