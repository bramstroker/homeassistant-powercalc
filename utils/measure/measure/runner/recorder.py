from collections.abc import Callable, Mapping, Sequence
import csv
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time

from measure.execution import ImmediateInteraction, MeasurementCancelledError, RunInteraction
from measure.request import RecorderMeasurementRequest, validate_export_filename
from measure.runner.const import DEFAULT_EXPORT_FILENAME
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasurementResult, MeasureUtil

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


@dataclass(frozen=True)
class RecorderEntityState:
    """Transport-neutral Home Assistant state captured beside one power reading."""

    state: str
    attributes: Mapping[str, object]


# Reads every requested entity in one go: the Home Assistant WebSocket API has no
# single-entity state command, so a per-entity reader refetches the whole state
# machine for each entity of each sample.
type EntityStateReader = Callable[[Sequence[str]], Mapping[str, RecorderEntityState]]


class RecorderRunner(MeasurementRunner[RecorderMeasurementRequest]):
    def __init__(
        self,
        measure_util: MeasureUtil,
        interaction: RunInteraction | None = None,
        entity_state_reader: EntityStateReader | None = None,
    ) -> None:
        self.measure_util = measure_util
        self.filename = DEFAULT_EXPORT_FILENAME
        self.interaction = interaction or ImmediateInteraction()
        self.entity_state_reader = entity_state_reader

    def writes_export_files(self) -> bool:
        return True

    def run(
        self,
        request: RecorderMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        self.filename = validate_export_filename(request.export_filename)
        self.interaction.confirm("Ready to start recording. Stop the measurement when you are finished.")
        self.interaction.phase("Starting recording")

        entity_ids = request.recorded_entity_ids
        if entity_ids and self.entity_state_reader is None:
            raise ValueError("A Home Assistant state reader is required when recorder entities are selected")

        output_directory = Path(export_directory).resolve()
        output_filepath = (output_directory / self.filename).resolve()
        if not output_filepath.is_relative_to(output_directory):
            raise ValueError("Recorder export path escapes its output directory")
        start_time = time.time()
        voltages: list[float] = []
        recorded = 0
        # Both Ctrl-C in the CLI and the app's Stop recording action are successful
        # terminal conditions for this intentionally open-ended runner.
        try:
            with output_filepath.open("w", encoding="utf-8", newline="") as output_file:
                writer = csv.writer(output_file) if not entity_ids else None
                while True:
                    timestamp = time.time()
                    self.interaction.notify("Measurement")
                    measurement = self.measure_util.take_measurement(timestamp)
                    _LOGGER.info("Measurement %.2f", measurement.power)
                    elapsed_seconds = timestamp - start_time
                    if entity_ids and self.entity_state_reader is not None:
                        entity_states = self._read_entity_states(entity_ids)
                        if entity_states is None:
                            self.interaction.wait(INTERVAL)
                            continue
                        entities: dict[str, object] = {}
                        live_states: dict[str, str] = {}
                        for entity_id in entity_ids:
                            entity_state = entity_states[entity_id]
                            live_states[entity_id] = entity_state.state
                            entities[entity_id] = {
                                "state": entity_state.state,
                                "attributes": dict(entity_state.attributes),
                            }
                        output_file.write(
                            json.dumps(
                                {
                                    "elapsed_seconds": elapsed_seconds,
                                    "power": measurement.power,
                                    "entities": entities,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                        )
                        output_file.write("\n")
                        self.interaction.entity_states(live_states)
                    elif writer is not None:
                        writer.writerow([elapsed_seconds, measurement.power])
                    voltages.extend(measurement.voltages)
                    recorded += 1
                    # Open-ended recording: report the running sample count (total 0 = indeterminate).
                    self.interaction.progress(recorded, 0, phase="Recording")
                    self.interaction.wait(INTERVAL)
        except KeyboardInterrupt, MeasurementCancelledError:
            _LOGGER.info("Stopped recording")

        summary = {
            "Samples recorded": str(recorded),
            "Duration": f"{round(time.time() - start_time)} s",
        }
        return RunnerResult(model_json_data={}, voltages=voltages, summary=summary)

    def _read_entity_states(self, entity_ids: Sequence[str]) -> Mapping[str, RecorderEntityState] | None:
        """Entity states for one sample, or None when Home Assistant could not answer.

        A reloading integration or a dropped WebSocket makes a single read fail; an
        open-ended recording that may run for hours skips that sample instead of ending.
        """

        if self.entity_state_reader is None:  # pragma: no cover - guarded by the caller
            return None
        try:
            return self.entity_state_reader(entity_ids)
        except MeasurementCancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            _LOGGER.warning("Skipping sample, could not read entity states: %s", error)
            return None

    def measure_standby_power(self) -> MeasurementResult:
        return MeasurementResult(power=0, voltages=[])
