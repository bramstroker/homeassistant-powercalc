from __future__ import annotations

from homeassistant_api.errors import HomeassistantAPIError

from measure.controller.errors import ControllerError
from measure.controller.fan.controller import FanController
from measure.controller.hass_controller import HassControllerBase
from measure.home_assistant import HomeAssistantManager


class HassFanController(HassControllerBase, FanController):
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        *,
        entity_id: str | None = None,
    ) -> None:
        super().__init__(home_assistant, entity_id=entity_id)

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
