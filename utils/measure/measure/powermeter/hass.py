from __future__ import annotations

import time
from typing import Any

import inquirer
from homeassistant_api import Client

from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID
from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.powermeter import ExtendedPowerMeasurementResult, PowerMeasurementResult, PowerMeter


class HassPowerMeter(PowerMeter):
    def __init__(self, api_url: str, token: str, call_update_entity: bool) -> None:
        self._call_update_entity = call_update_entity
        self._entity_id: str | None = None
        self._voltage_entity_id: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
        except Exception as e:
            raise PowerMeterError(f"Failed to connect to HA API: {e}") from e

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult | ExtendedPowerMeasurementResult:
        """Get a new power reading from Hass-API. Optionally include voltage."""
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
        power_value = float(state.state)

        if include_voltage:
            if not self._voltage_entity_id:
                self._voltage_entity_id = self.find_voltage_entity()
                if not self._voltage_entity_id:
                    raise UnsupportedFeatureError("No matching voltage entity found.")

            voltage_state = self.client.get_state(entity_id=self._voltage_entity_id)
            if voltage_state == "unavailable":
                raise PowerMeterError(f"Voltage sensor {self._voltage_entity_id} unavailable")

            voltage_value = float(voltage_state.state)
            return ExtendedPowerMeasurementResult(power_value, voltage_value, last_updated)

        return PowerMeasurementResult(power_value, last_updated)

    def find_voltage_entity(self) -> str | None:
        """Try to find a matching voltage entity for the current power entity."""
        matched_sensors = self.match_power_and_voltage_sensors()
        return matched_sensors.get(self._entity_id)

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

    def get_voltage_sensors(self) -> list[str]:
        entities = self.client.get_entities()
        sensors = entities["sensor"].entities.values()
        voltage_sensors = [entity.entity_id for entity in sensors if entity.state.attributes.get("unit_of_measurement") == "V"]
        return sorted(voltage_sensors)

    def match_power_and_voltage_sensors(self) -> dict[str, str]:
        power_sensors = self.get_power_sensors()
        voltage_sensors = self.get_voltage_sensors()

        # Create mappings based on base names
        power_map = {sensor.rsplit("_power", 1)[0]: sensor for sensor in power_sensors}
        voltage_map = {sensor.rsplit("_voltage", 1)[0]: sensor for sensor in voltage_sensors}

        matched_sensors = {}
        for base_name, power_sensor in power_map.items():
            if base_name in voltage_map:
                matched_sensors[power_sensor] = voltage_map[base_name]

        return matched_sensors

    def process_answers(self, answers: dict[str, Any]) -> None:
        self._entity_id = answers[QUESTION_POWERMETER_ENTITY_ID]
