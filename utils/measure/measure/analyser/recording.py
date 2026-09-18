from collections.abc import Mapping, Sequence
from dataclasses import replace
import json
import math
from pathlib import Path

from measure.recording.models import (
    LoadedRecording,
    RecordedEntity,
    RecordedEntityState,
    RecordingContext,
    RecordingDataset,
    RecordingSample,
)


def load_recording(path: Path) -> LoadedRecording:
    """Load typed recorder JSONL while accepting recordings from before format v1."""

    samples: list[RecordingSample] = []
    invalid_records: list[str] = []
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
                invalid_records.append(f"line {line_number}: {error}")
                continue
            samples.append(sample)
    warnings: list[str] = []
    if invalid_records:
        warnings.append(f"Skipped {len(invalid_records)} invalid recorder line(s); first was {invalid_records[0]}")
    return LoadedRecording(RecordingDataset(samples, metadata), warnings)


def load_recordings(paths: Sequence[Path]) -> LoadedRecording:
    if not paths:
        raise ValueError("Select at least one recording")
    loaded = [load_recording(path) for path in paths]
    metadata = loaded[0].dataset.metadata
    for recording in loaded[1:]:
        other = recording.dataset.metadata
        if (
            metadata is not None
            and other is not None
            and (
                any(metadata.get(key) != other.get(key) for key in ("recipe", "primary_entity_id"))
                or _normalize_selected_entity_metadata(metadata) != _normalize_selected_entity_metadata(other)
            )
        ):
            raise ValueError("Combined recordings must describe the same recipe and entities")
    return LoadedRecording(
        RecordingDataset(
            [
                replace(sample, recording_id=index)
                for index, recording in enumerate(loaded)
                for sample in recording.dataset.samples
            ],
            metadata,
        ),
        [warning for recording in loaded for warning in recording.warnings],
    )


def _normalize_selected_entity_metadata(metadata: Mapping[str, object]) -> list[RecordedEntity]:
    """Compare entity identities and signal metadata independently of live availability."""
    return [
        replace(entity, has_live_state=None, disabled_by=None)
        for entity in _parse_metadata_entities(metadata.get("entities"))
    ]


def restore_recording_context(fallback: RecordingContext, metadata: Mapping[str, object] | None) -> RecordingContext:
    """Reanalyse using captured registry metadata, without contacting Home Assistant.

    Requests still choose the recipe, primary entity, and roles. A metadata header
    cannot silently change those choices or promote inventory-only entities.
    """
    if (
        metadata is None
        or metadata.get("recipe") != fallback.recipe
        or metadata.get("primary_entity_id") != fallback.primary_entity_id
    ):
        return fallback
    entities = {entity.entity_id: entity for entity in _parse_metadata_entities(metadata.get("entities"))}
    selected = [
        replace(entities[entity.entity_id], role=entity.role) if entity.entity_id in entities else entity
        for entity in fallback.entities
    ]
    return RecordingContext(
        recipe=fallback.recipe,
        primary_entity_id=fallback.primary_entity_id,
        device_type=fallback.device_type,
        entities=selected,
        device_entities=_parse_metadata_entities(metadata.get("device_entities")),
    )


def _parse_metadata_entities(value: object) -> list[RecordedEntity]:
    if not isinstance(value, list):
        return []
    result: list[RecordedEntity] = []
    for item in value:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) for key in ("entity_id", "domain", "role")
        ):
            continue
        optional: dict[str, str | None] = {
            key: item.get(key) if isinstance(item.get(key), str) else None
            for key in (
                "device_class",
                "integration",
                "translation_key",
                "device_id",
                "unit",
                "disabled_by",
            )
        }
        result.append(
            RecordedEntity(
                item["entity_id"],
                item["domain"],
                item["role"],
                **optional,
                has_live_state=item.get("has_live_state") if isinstance(item.get("has_live_state"), bool) else None,
            )
        )
    return result


def _parse_sample(record: dict[str, object]) -> RecordingSample:
    elapsed_seconds = _parse_number(record["elapsed_seconds"])
    power = _parse_number(record["power"])
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


def _parse_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError("expected a number")
    return float(value)
