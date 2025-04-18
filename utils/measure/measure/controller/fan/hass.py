from __future__ import annotations

from typing import Any

import inquirer
from homeassistant_api import Client, HomeassistantAPIError

from measure.const import QUESTION_ENTITY_ID
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.errors import ControllerError
from measure.controller.fan.controller import FanController


class HassFanController(FanController):
    def __init__(self, api_url: str, token: str) -> None:
        self.charging_device_type: ChargingDeviceType | None = None
        self.entity_id: str | None = None
        self.battery_level_attribute: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
            self.client.get_config()
        except HomeassistantAPIError as e:
            raise ControllerError(f"Failed to connect to HA API: {e}") from e

    def set_percentage(self, percentage: int) -> None:
        try:
            self.client.trigger_service("fan", "set_percentage", percentage=percentage, entity_id=self.entity_id)
        except HomeassistantAPIError as e:
            raise ControllerError(f"Failed to set fan percentage: {e}") from e

    def turn_off(self) -> None:
        try:
            self.client.trigger_service("fan", "turn_off", entity_id=self.entity_id)
        except HomeassistantAPIError as e:
            raise ControllerError(f"Failed to turn off fan: {e}") from e

    def get_questions(self) -> list[inquirer.questions.Question]:
        def get_domain_entity_list(domain: str) -> list:
            entities = self.client.get_entities()
            if domain not in entities:
                return []
            found_entities = entities[domain].entities.values()
            return sorted([entity.entity_id for entity in found_entities])

        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the fan entity",
                choices=get_domain_entity_list("fan"),
            ),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        self.entity_id = answers[QUESTION_ENTITY_ID]
