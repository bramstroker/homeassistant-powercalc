"""Automated relay self-consumption measurement."""

from collections import defaultdict
import logging
from pathlib import Path
from statistics import mean
import time
from typing import TypedDict

from measure.controller.switch.hass import HassSwitchController
from measure.request import SmartSwitchMeasurementRequest
from measure.runner.interaction import RunInteraction
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.utils.files import write_json_atomic
from measure.utils.sampling import MeasurementResult, PowerSampler

_LOGGER = logging.getLogger("measure")


class StateReading(TypedDict):
    cycle: int
    state: str
    powers: list[float]
    mean: float


class SmartSwitchRunner(MeasurementRunner[SmartSwitchMeasurementRequest]):
    def __init__(self, sampler: PowerSampler, controller: HassSwitchController, interaction: RunInteraction) -> None:
        self.sampler = sampler
        self.controller = controller
        self.interaction = interaction

    def run(self, request: SmartSwitchMeasurementRequest, export_directory: str) -> RunnerResult:
        """Repeat all-off and relay-on states, then validate their power increments."""

        entity_ids = self.controller.entity_ids
        multi = len(entity_ids) > 1
        states = ["off", *entity_ids, *(["all_on"] if multi else [])]
        total = request.repeat_cycles * len(states)
        readings: list[StateReading] = []
        voltages: list[float] = []
        self.controller.remember_states()
        try:
            for cycle in range(request.repeat_cycles):
                for state in states:
                    self.interaction.checkpoint()
                    active = state if state in entity_ids else None
                    self.controller.set_states(active, all_on=state == "all_on")
                    self.interaction.phase(f"Settling relays: {state} (cycle {cycle + 1})")
                    self.interaction.wait(request.settle_seconds)
                    self.controller.verify_states(active, all_on=state == "all_on")
                    powers: list[float] = []
                    for sample in range(request.samples_per_state):
                        self.interaction.checkpoint()
                        if sample:
                            self.interaction.wait(request.parameters.sleep_time)
                        result = self.sampler.take_measurement(time.time())
                        powers.append(result.power)
                        voltages.extend(result.voltages)
                    readings.append({"cycle": cycle + 1, "state": state, "powers": powers, "mean": mean(powers)})
                    self.interaction.progress(
                        cycle * len(states) + states.index(state) + 1,
                        total,
                        phase="Measuring relay self consumption",
                    )
        finally:
            # Cleanup also runs after validation below; this immediately restores relays after sampling.
            self.controller.restore_states()

        evidence = Path(export_directory) / "smart_switch_readings.json"
        write_json_atomic(evidence, {"entity_ids": entity_ids, "readings": readings})
        model = self._create_model(request, readings)
        return RunnerResult(model_json_data=model, voltages=voltages)

    def _create_model(
        self,
        request: SmartSwitchMeasurementRequest,
        readings: list[StateReading],
    ) -> dict[str, object]:
        entity_ids = self.controller.entity_ids
        multi = len(entity_ids) > 1
        powers_by_state: dict[str, list[float]] = defaultdict(list)
        for reading in readings:
            powers_by_state[reading["state"]].append(reading["mean"])
        baselines = powers_by_state["off"]
        baseline = mean(baselines)
        if baseline < 0.05:
            raise ValueError(
                "The meter did not resolve the switch's off-state self consumption; "
                "use a more precise meter or a calibrated dummy load"
            )

        increments: list[float] = []
        for entity_id in entity_ids:
            for on_power, off_power in zip(powers_by_state[entity_id], baselines, strict=True):
                increments.append(on_power - off_power)
        increment = mean(increments)
        tolerance = max(0.10, abs(increment) * 0.20)
        if increment <= 0 or any(abs(value - increment) > tolerance for value in increments):
            raise ValueError(
                f"Relay increments differ too much for one profile "
                f"(mean {increment:.3f} W, tolerance {tolerance:.3f} W); "
                "review smart_switch_readings.json"
            )
        if multi:
            self._validate_all_on(powers_by_state["all_on"], baselines, len(entity_ids), increment)

        model: dict[str, object] = {
            "device_type": "smart_switch",
            "device_specs": {"power_monitoring": request.power_monitoring},
            "standby_power": round(baseline, 3),
        }
        if multi:
            model.update(
                calculation_strategy="multi_switch",
                discovery_by="device",
                only_self_usage=True,
                multi_switch_config={"power": round(increment, 3)},
            )
        else:
            model["calculation_strategy"] = "fixed"
            model["standby_power_on"] = round(baseline + increment, 3)
            if request.power_monitoring:
                model["only_self_usage"] = True
        return model

    @staticmethod
    def _validate_all_on(all_on: list[float], baselines: list[float], relay_count: int, increment: float) -> None:
        expected = relay_count * increment
        tolerance = max(0.10, abs(expected) * 0.20)
        for all_power, off_power in zip(all_on, baselines, strict=True):
            if abs((all_power - off_power) - expected) > tolerance:
                raise ValueError(
                    "All-on power does not match the sum of relay increments; review smart_switch_readings.json"
                )

    def measure_standby_power(self) -> MeasurementResult | None:
        return None

    def cleanup(self) -> None:
        try:
            self.controller.restore_states()
        except Exception:
            _LOGGER.warning("Could not restore smart switch relays during cleanup", exc_info=True)
