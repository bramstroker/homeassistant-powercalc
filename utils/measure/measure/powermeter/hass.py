from __future__ import annotations

from collections.abc import Callable
import time

from homeassistant_api import BaseEntity

from measure.home_assistant import HomeAssistantManager
from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class HassPowerMeter(PowerMeter):
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        call_update_entity: bool,
        *,
        entity_id: str | None = None,
        voltage_entity_id: str | None = None,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._call_update_entity = call_update_entity
        self._entity_id = entity_id
        self._voltage_entity_id = voltage_entity_id
        self._entities: list[BaseEntity] | None = None
        self._wait = wait
        self.client = home_assistant

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a new power reading from Home Assistant. Optionally include voltage."""
        if self._call_update_entity:
            self.client.trigger_service(
                "homeassistant",
                "update_entity",
                entity_id=self._entity_id,
            )
            self._wait(1)

        state = self.client.get_state(entity_id=self._entity_id)
        if state.state == "unavailable":
            raise PowerMeterError(f"Power sensor {self._entity_id} unavailable")
        last_updated = state.last_updated.timestamp() if state.last_updated is not None else time.time()
        power_value = float(state.state)

        # Availability of the voltage entity is checked by the read below; avoid the
        # extra has_voltage_support() round-trip on every measurement.
        if include_voltage and not self._voltage_entity_id:
            raise UnsupportedFeatureError("Voltage sensor entity not found.")

        if include_voltage:
            voltage_state = self.client.get_state(entity_id=self._voltage_entity_id)
            if voltage_state.state == "unavailable":
                raise PowerMeterError(f"Voltage sensor {self._voltage_entity_id} unavailable")

            voltage_value = float(voltage_state.state)
            return PowerMeasurementResult(
                power=power_value,
                voltage=voltage_value,
                updated=last_updated,
            )

        return PowerMeasurementResult(power=power_value, updated=last_updated)

    def has_voltage_support(self) -> bool:
        if not self._voltage_entity_id:
            return False

        voltage_state = self.client.get_state(entity_id=self._voltage_entity_id)
        if voltage_state.state == "unavailable":
            raise PowerMeterError(f"Voltage sensor {self._voltage_entity_id} unavailable")
        return True

    def autodetect_voltage_entity(self, power_entity: str) -> bool:
        """Try to find a matching voltage entity for the current power entity."""
        matched_sensors = self.match_power_and_voltage_sensors()

        if not matched_sensors or power_entity not in matched_sensors:
            # no match found for our power sensor
            return False

        self._voltage_entity_id = matched_sensors.get(power_entity)
        return True

    def get_power_sensors(self) -> list[str]:
        return self.get_entities_by_unit_of_measurement("W")

    def get_voltage_sensors(self) -> list[str]:
        return self.get_entities_by_unit_of_measurement("V")

    def get_entities_by_unit_of_measurement(self, unit_of_measurement: str) -> list[str]:
        return sorted(
            [
                entity.entity_id
                for entity in self.get_entities()
                if entity.state.attributes.get("unit_of_measurement") == unit_of_measurement
            ],
        )

    def get_entities(self) -> list[BaseEntity]:
        if not self._entities:
            entities = self.client.get_entities()
            self._entities = list(entities["sensor"].entities.values())
        return self._entities

    def match_power_and_voltage_sensors(self) -> dict[str, str]:
        registry = {entry.entity_id: entry for entry in self.client.list_entity_registry()}
        voltage_by_device: dict[str, str] = {}
        for entity_id in self.get_voltage_sensors():
            entry = registry.get(entity_id)
            if entry is not None and entry.device_id is not None:
                voltage_by_device.setdefault(entry.device_id, entity_id)

        matched_sensors: dict[str, str] = {}
        for entity_id in self.get_power_sensors():
            entry = registry.get(entity_id)
            if entry is not None and entry.device_id in voltage_by_device:
                matched_sensors[entity_id] = voltage_by_device[entry.device_id]
        return matched_sensors
