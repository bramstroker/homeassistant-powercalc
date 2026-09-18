from collections.abc import Callable, Mapping, Sequence
import csv
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time
from typing import TextIO

from measure.cancellation import MeasurementCancelledError
from measure.recording.capture import build_vacuum_attribute_policy, filter_vacuum_recording_attributes
from measure.recording.context import build_recording_context
from measure.recording.files import DEFAULT_EXPORT_FILENAME
from measure.recording.models import RecordingContext
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe, validate_export_filename
from measure.runner.interaction import ImmediateInteraction, RunInteraction
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.utils.sampling import MeasurementResult, PowerSampler

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


@dataclass(frozen=True)
class RecorderEntityState:
    """Transport-neutral Home Assistant state captured beside one power reading."""

    state: str
    attributes: Mapping[str, object]


@dataclass(frozen=True)
class CapturedEntities:
    """Entity data for the recording file and the live session display."""

    recorded: Mapping[str, object]
    live_states: Mapping[str, str]


# Reads every requested entity in one go: the Home Assistant WebSocket API has no
# single-entity state command, so a per-entity reader refetches the whole state
# machine for each entity of each sample.
type EntityStateReader = Callable[[Sequence[str]], Mapping[str, RecorderEntityState]]


class RecorderRunner(MeasurementRunner[RecorderMeasurementRequest]):
    def __init__(
        self,
        sampler: PowerSampler,
        interaction: RunInteraction | None = None,
        entity_state_reader: EntityStateReader | None = None,
        recording_context: RecordingContext | None = None,
    ) -> None:
        self.sampler = sampler
        self.filename = DEFAULT_EXPORT_FILENAME
        self.interaction = interaction or ImmediateInteraction()
        self.entity_state_reader = entity_state_reader
        self.recording_context = recording_context
        self._missing_optional_entities: set[str] = set()

    def writes_export_files(self) -> bool:
        return True

    def run(
        self,
        request: RecorderMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        self.filename = validate_export_filename(request.export_filename)
        self._missing_optional_entities.clear()
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
                if entity_ids:
                    _write_jsonl(output_file, self._build_metadata(request))
                while True:
                    timestamp = time.time()
                    self.interaction.notify("Measurement")
                    measurement = self.sampler.take_measurement(timestamp)
                    _LOGGER.info("Measurement %.2f", measurement.power)
                    elapsed_seconds = timestamp - start_time
                    if self._write_sample(output_file, request, elapsed_seconds, measurement.power):
                        voltages.extend(measurement.voltages)
                        recorded += 1
                        # Open-ended recording: total 0 means indeterminate progress.
                        self.interaction.progress(recorded, 0, phase="Recording")
                    self.interaction.wait(INTERVAL)
        except KeyboardInterrupt, MeasurementCancelledError:
            _LOGGER.info("Stopped recording")

        summary = {
            "Samples recorded": str(recorded),
            "Duration": f"{round(time.time() - start_time)} s",
        }
        if self._missing_optional_entities:
            summary["Optional entities missing during recording"] = ", ".join(sorted(self._missing_optional_entities))
        return RunnerResult(model_json_data={}, voltages=voltages, summary=summary)

    def _write_sample(
        self, output_file: TextIO, request: RecorderMeasurementRequest, elapsed_seconds: float, power: float
    ) -> bool:
        """Write one sample, returning False when entity capture requires skipping it."""
        entity_ids = request.recorded_entity_ids
        if not entity_ids:
            csv.writer(output_file).writerow([elapsed_seconds, power])
            return True

        is_vacuum = request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT
        required_ids = entity_ids[:2] if is_vacuum else entity_ids
        entity_states = self._read_entity_states(entity_ids, required_ids)
        if entity_states is None:
            return False
        captured = self._sample_entities(entity_ids, entity_states, is_vacuum=is_vacuum)
        _write_jsonl(
            output_file,
            {
                "record_type": "sample",
                "elapsed_seconds": elapsed_seconds,
                "power": power,
                "entities": captured.recorded,
            },
        )
        self.interaction.entity_states(captured.live_states)
        return True

    def _build_metadata(self, request: RecorderMeasurementRequest) -> dict[str, object]:
        metadata = (self.recording_context or build_recording_context(request)).build_metadata_record()
        if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT:
            metadata["attribute_policy"] = build_vacuum_attribute_policy()
        return metadata

    def _sample_entities(
        self,
        entity_ids: Sequence[str],
        entity_states: Mapping[str, RecorderEntityState],
        *,
        is_vacuum: bool,
    ) -> CapturedEntities:
        entities: dict[str, object] = {}
        live_states: dict[str, str] = {}
        for entity_id in entity_ids:
            entity_state = entity_states.get(entity_id)
            if entity_state is None:
                if entity_id not in self._missing_optional_entities:
                    _LOGGER.warning("Optional recording entity disappeared: %s", entity_id)
                    self._missing_optional_entities.add(entity_id)
                entity_state = RecorderEntityState("unavailable", {})
            live_states[entity_id] = entity_state.state
            entities[entity_id] = {
                "state": entity_state.state,
                "attributes": filter_vacuum_recording_attributes(entity_state.attributes)
                if is_vacuum
                else dict(entity_state.attributes),
            }
        return CapturedEntities(recorded=entities, live_states=live_states)

    def _read_entity_states(
        self,
        entity_ids: Sequence[str],
        required_ids: Sequence[str],
    ) -> Mapping[str, RecorderEntityState] | None:
        """Entity states for one sample, or None when Home Assistant could not answer.

        A reloading integration or a dropped WebSocket makes a single read fail; an
        open-ended recording that may run for hours skips that sample instead of ending.
        """

        assert self.entity_state_reader is not None
        try:
            states = self.entity_state_reader(entity_ids)
            if missing := sorted(set(required_ids) - states.keys()):
                raise ValueError(f"Required recording entities not found: {', '.join(missing)}")
            return states
        except MeasurementCancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            _LOGGER.warning("Skipping sample, could not read entity states: %s", error)
            return None

    def measure_standby_power(self) -> MeasurementResult:
        return MeasurementResult(power=0, voltages=[])


def _write_jsonl(output_file: TextIO, record: Mapping[str, object]) -> None:
    output_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
