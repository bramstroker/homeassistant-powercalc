from __future__ import annotations

from collections.abc import Callable
import time

from measure.home_assistant import HomeAssistantManager
from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter, PowerMeterDiagnosticSample


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

    def diagnostic_sample(self) -> PowerMeterDiagnosticSample:
        """Read the raw HA state and its source reporting timestamp without forcing an update."""

        state = self.client.get_state(entity_id=self._entity_id)
        if state.state in {"unavailable", "unknown"}:
            raise PowerMeterError(f"Power sensor {self._entity_id} {state.state}")
        reported = state.last_reported or state.last_updated
        return PowerMeterDiagnosticSample(
            power=float(state.state),
            raw_value=state.state,
            reported_at=reported.timestamp() if reported is not None else time.time(),
        )
