from __future__ import annotations

import inquirer
from homeassistant_api.errors import HomeassistantAPIError

from measure.const import QUESTION_ENTITY_ID
from measure.controller.errors import ControllerError
from measure.controller.fan.controller import FanController
from measure.controller.hass_controller import HassControllerBase


class HassFanController(HassControllerBase, FanController):
    def set_percentage(self, percentage: int) -> None:
        assert percentage >= 0
        assert percentage <= 100
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
        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the fan entity",
                choices=self.get_domain_entity_list("fan"),
            ),
        ]
