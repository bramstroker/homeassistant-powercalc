import json
import math
from pathlib import Path

from measure.analyser.models import LoadedRecording, RecordedEntityState, RecordingDataset, RecordingSample


def load_recording(path: Path) -> LoadedRecording:
    """Load typed recorder JSONL while accepting recordings from before format v1."""

    samples: list[RecordingSample] = []
    invalid_records: list[tuple[int, str]] = []
    metadata: dict[str, object] | None = None
    with path.open(encoding="utf-8") as recording:
        for line_number, line in enumerate(recording, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("record is not an object")
                if record.get("record_type") == "metadata":
                    metadata = record
                    continue
                if record.get("record_type") not in (None, "sample"):
                    continue
                sample = _parse_sample(record)
            except (KeyError, ValueError, TypeError) as error:
                invalid_records.append((line_number, str(error)))
                continue
            samples.append(sample)
    warnings: tuple[str, ...] = ()
    if invalid_records:
        line_number, failure_reason = invalid_records[0]
        warnings = (
            f"Skipped {len(invalid_records)} invalid recorder line(s); first was line {line_number}: {failure_reason}",
        )
    return LoadedRecording(RecordingDataset(tuple(samples), metadata), warnings)


def _parse_sample(record: dict[str, object]) -> RecordingSample:
    elapsed_seconds = _number(record["elapsed_seconds"])
    power = _number(record["power"])
    if not math.isfinite(elapsed_seconds) or not math.isfinite(power):
        raise ValueError("elapsed time and power must be finite")
    raw_entities = record["entities"]
    if not isinstance(raw_entities, dict):
        raise ValueError("entities must be an object")
    entities: dict[str, RecordedEntityState] = {}
    for entity_id, raw_state in raw_entities.items():
        if not isinstance(entity_id, str) or not isinstance(raw_state, dict):
            raise ValueError("entity states must be objects")
        state = raw_state.get("state")
        attributes = raw_state.get("attributes", {})
        if not isinstance(state, str) or not isinstance(attributes, dict):
            raise ValueError("entity state must be a string and attributes an object")
        entities[entity_id] = RecordedEntityState(state, attributes)
    return RecordingSample(elapsed_seconds, power, entities)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError("expected a number")
    return float(value)
