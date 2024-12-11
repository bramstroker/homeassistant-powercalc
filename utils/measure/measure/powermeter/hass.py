from __future__ import annotations

import time
from typing import Any

import inquirer
from homeassistant_api import Client

from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class HassPowerMeter(PowerMeter):
    def __init__(self, api_url: str, token: str, call_update_entity: bool) -> None:
        self._call_update_entity = call_update_entity
        self._entity_id: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
        except Exception as e:
            raise PowerMeterError(f"Failed to connect to HA API: {e}") from e

    def get_power(self) -> PowerMeasurementResult:
        if self._call_update_entity:
            self.client.trigger_service(
                "homeassistant",
                "update_entity",
                entity_id=self._entity_id,
            )
            time.sleep(1)

        state = self.client.get_state(entity_id=self._entity_id)
        if state == "unavailable":
            raise PowerMeterError(f"Power sensor {self._entity_id} unavailable")
        last_updated = state.last_updated.timestamp()
        return PowerMeasurementResult(float(state.state), last_updated)

    def get_questions(self) -> list[inquirer.questions.Question]:
        power_sensor_list = self.get_power_sensors()

        return [
            inquirer.List(
                name=QUESTION_POWERMETER_ENTITY_ID,
                message="Select the powermeter",
                choices=power_sensor_list,
            ),
        ]

    def get_power_sensors(self) -> list[str]:
        entities = self.client.get_entities()
        sensors = entities["sensor"].entities.values()
        power_sensors = [entity.entity_id for entity in sensors if entity.state.attributes.get("unit_of_measurement") == "W"]
        return sorted(power_sensors)

    def process_answers(self, answers: dict[str, Any]) -> None:
        self._entity_id = answers[QUESTION_POWERMETER_ENTITY_ID]
