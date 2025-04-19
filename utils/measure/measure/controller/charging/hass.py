from __future__ import annotations

from typing import Any

import inquirer

from measure.const import QUESTION_ENTITY_ID
from measure.controller.charging.const import QUESTION_BATTERY_LEVEL_ATTRIBUTE, ChargingDeviceType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.hass_controller import HassControllerBase
from measure.runner.const import QUESTION_CHARGING_DEVICE_TYPE

DEVICE_TYPE_DOMAIN = {
    ChargingDeviceType.VACUUM_ROBOT: "vacuum",
}

ATTR_BATTERY_LEVEL = "battery_level"


class HassChargingController(HassControllerBase, ChargingController):
    def __init__(self, api_url: str, token: str) -> None:
        self.charging_device_type: ChargingDeviceType | None = None
        self.battery_level_attribute: str | None = None
        super().__init__(api_url, token)

    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""

        state = self.get_entity_state()
        if self.battery_level_attribute not in state.attributes:
            raise BatteryLevelRetrievalError(f"Attribute {self.battery_level_attribute} not found in entity {self.entity_id}")
        return int(state.attributes[self.battery_level_attribute])

    def is_charging(self) -> bool:
        """Check if the device is currently charging"""

        return self.get_entity_state().state == "docked"

    def is_valid_state(self) -> bool:
        """Check if the entity is in a valid state where it is available, either charging or performing tasks"""

        return self.get_entity_state().state in ["docked", "cleaning", "returning", "idle", "paused"]

    def get_questions(self) -> list[inquirer.questions.Question]:
        def get_entity_list(answers: dict[str, Any]) -> list:
            domain = DEVICE_TYPE_DOMAIN.get(ChargingDeviceType(answers[QUESTION_CHARGING_DEVICE_TYPE]), "sensor")
            return self.get_domain_entity_list(domain)

        def get_attribute_list(answers: dict[str, Any]) -> list:
            entity = self.client.get_entity(entity_id=answers[QUESTION_ENTITY_ID])
            return sorted(entity.state.attributes.keys())

        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the vacuum entity",
                choices=get_entity_list,
            ),
            inquirer.List(
                name=QUESTION_BATTERY_LEVEL_ATTRIBUTE,
                message="Select the battery_level attribute",
                choices=get_attribute_list,
                ignore=lambda x: ATTR_BATTERY_LEVEL in get_attribute_list(x),
            ),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        self.charging_device_type = answers[QUESTION_CHARGING_DEVICE_TYPE]
        self.battery_level_attribute = answers.get(QUESTION_BATTERY_LEVEL_ATTRIBUTE) or ATTR_BATTERY_LEVEL
        super().process_answers(answers)
