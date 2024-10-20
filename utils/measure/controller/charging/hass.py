from __future__ import annotations

from typing import Any

import inquirer
from controller.errors import ControllerError
from homeassistant_api import Client, HomeassistantAPIError

from .const import ChargingDeviceType
from .controller import ChargingController


class HassChargingController(ChargingController):
    def __init__(self, api_url: str, token: str) -> None:
        self.charging_device_type: ChargingDeviceType | None = None
        self.entity_id: ChargingDeviceType | None = None
        self.battery_level_attribute: str | None = None
        self.battery_level_entity_id: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
            self.client.get_config()
        except HomeassistantAPIError as e:
            raise ControllerError(f"Failed to connect to HA API: {e}") from e

    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""
        if self.battery_level_attribute:
            entity = self.client.get_entity(entity_id=self.entity_id)
            return int(entity.state.attributes[self.battery_level_attribute])

        entity_info = self.client.get_entity(entity_id=self.battery_level_entity_id)
        return int(entity_info.state.state)

    def is_charging(self) -> bool:
        """Check if the device is currently charging"""
        entity = self.client.get_entity(self.entity_id)
        return entity.state.attributes["docked"]

    def get_questions(self) -> list[inquirer.questions.Question]:
        def get_entity_list(answers: dict[str, Any]) -> list:
            domain = "vacuum" if answers["charging_device_type"] == ChargingDeviceType.VACUUM else "sensor"
            return get_domain_entity_list(domain)

        def get_attribute_list(answers: dict[str, Any]) -> list:
            entity = self.client.get_entity(entity_id=answers["charging_entity_id"])
            return sorted(entity.state.attributes.keys())

        def get_domain_entity_list(domain: str) -> list:
            entities = self.client.get_entities()
            if domain not in entities:
                return []
            found_entities = entities[domain].entities.values()
            return sorted([entity.entity_id for entity in found_entities])

        return [
            inquirer.List(
                name="charging_device_type",
                message="Select the charging device type",
                choices=[(charging_device_type.value, charging_device_type) for charging_device_type in ChargingDeviceType],
            ),
            inquirer.List(
                name="charging_entity_id",
                message="Select the charging entity",
                choices=get_entity_list,
            ),
            inquirer.List(
                name="charging_battery_level_is_attribute",
                message="Is battery level an attribute of the entity or a separate entity?",
                choices=["attribute", "entity"],
            ),
            inquirer.List(
                name="charging_battery_level_attribute",
                message="Select the battery_level attribute",
                ignore=lambda answers: answers.get("charging_battery_level_is_attribute") != "attribute",
                choices=get_attribute_list,
            ),
            inquirer.List(
                name="charging_battery_level_entity",
                message="Select the battery_level entity",
                ignore=lambda answers: answers.get("charging_battery_level_is_attribute") != "entity",
                choices=get_domain_entity_list("sensor"),
            ),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        self.entity_id = answers["charging_entity_id"]
        self.charging_device_type = answers["charging_device_type"]
        self.battery_level_attribute = answers["charging_battery_level_attribute"]
        self.battery_level_entity_id = answers["charging_battery_level_entity"]
