from __future__ import annotations

from typing import Any

import inquirer
from dateutil.parser import parse
from homeassistant_api import Client

from .errors import PowerMeterError
from .powermeter import PowerMeasurementResult, PowerMeter


class HassPowerMeter(PowerMeter):
    def __init__(self, api_url: str, token: str):
        try:
            self.client = Client(api_url, token)
        except Exception as e:
            raise PowerMeterError(f"Failed to connect to HA API: {e}")

    def get_power(self) -> PowerMeasurementResult:
        state = self.client.get_state(self._entity_id)
        last_updated = parse(state.get("last_updated")).timestamp()
        return PowerMeasurementResult(float(state.get("state")), last_updated)

    def get_questions(self) -> list[dict]:
        power_sensor_list = self.get_power_sensors()

        return [
            inquirer.List(
                name="powermeter_entity_id",
                message="Select the powermeter",
                choices=power_sensor_list
            )
        ]

    def get_power_sensors(self) -> list[str]:
        entities = self.client.get_entities()
        sensors = entities["sensor"].entities.values()
        power_sensors = [
            entity.entity_id for entity in sensors if 
            hasattr(entity.state, 'attributes') and 
            hasattr(entity.state.attributes, 'unit_of_measurement') and 
            entity.state.attributes['unit_of_measurement'] == "W"
        ]
        return sorted(power_sensors)

    def process_answers(self, answers: dict[str, Any]):
        self._entity_id = answers["powermeter_entity_id"]
