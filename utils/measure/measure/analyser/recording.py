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
    RecordingMetadata,
    RecordingSample,
)


def load_recording(path: Path, *, recording_id: int = 0) -> LoadedRecording:
    """Load typed recorder JSONL while accepting recordings from before format v1."""

    samples: list[RecordingSample] = []
    invalid_count = 0
    first_invalid: str | None = None
    metadata: RecordingMetadata | None = None
    with path.open(encoding="utf-8") as recording:
        for line_number, line in enumerate(recording, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("record is not an object")
                if record.get("record_type") == "metadata":
                    metadata = _parse_metadata(record)
                    continue
                if record.get("record_type") not in (None, "sample"):
                    continue
                sample = _parse_sample(record, recording_id)
            except (KeyError, ValueError, TypeError) as error:
                invalid_count += 1
                if first_invalid is None:
                    first_invalid = f"line {line_number}: {error}"
                continue
            samples.append(sample)
    warnings: list[str] = []
    if invalid_count:
        warnings.append(f"Skipped {invalid_count} invalid recorder line(s); first was {first_invalid}")
    return LoadedRecording(RecordingDataset(samples, metadata), warnings)


def load_recordings(paths: Sequence[Path]) -> LoadedRecording:
    if not paths:
        raise ValueError("Select at least one recording")
    first = load_recording(paths[0])
    metadata = first.dataset.metadata
    selected_entities = _normalize_selected_entity_metadata(metadata) if metadata is not None else []
    samples = first.dataset.samples
    warnings = first.warnings
    for index, path in enumerate(paths[1:], start=1):
        recording = load_recording(path, recording_id=index)
        other = recording.dataset.metadata
        if (
            metadata is not None
            and other is not None
            and (
                metadata.recipe != other.recipe
                or metadata.primary_entity_id != other.primary_entity_id
                or selected_entities != _normalize_selected_entity_metadata(other)
            )
        ):
            raise ValueError("Combined recordings must describe the same recipe and entities")
        samples.extend(recording.dataset.samples)
        warnings.extend(recording.warnings)
    return LoadedRecording(RecordingDataset(samples, metadata), warnings)


def _normalize_selected_entity_metadata(metadata: RecordingMetadata) -> list[RecordedEntity]:
    """Compare entity identities and signal metadata independently of live availability."""
    return [replace(entity, has_live_state=None, disabled_by=None) for entity in metadata.entities]


def restore_recording_context(fallback: RecordingContext, metadata: RecordingMetadata | None) -> RecordingContext:
    """Reanalyse using captured registry metadata, without contacting Home Assistant.

    Requests still choose the recipe, primary entity, and roles. A metadata header
    cannot silently change those choices or promote inventory-only entities.
    """
    if (
        metadata is None
        or metadata.recipe != fallback.recipe
        or metadata.primary_entity_id != fallback.primary_entity_id
    ):
        return fallback
    entities = {entity.entity_id: entity for entity in metadata.entities}
    selected = [
        replace(entities[entity.entity_id], role=entity.role) if entity.entity_id in entities else entity
        for entity in fallback.entities
    ]
    return RecordingContext(
        recipe=fallback.recipe,
        primary_entity_id=fallback.primary_entity_id,
        device_type=fallback.device_type,
        entities=selected,
        device_entities=metadata.device_entities,
        related_device_ids=metadata.related_device_ids,
    )


def _parse_metadata(record: Mapping[str, object]) -> RecordingMetadata:
    recipe = record.get("recipe")
    primary_entity_id = record.get("primary_entity_id")
    return RecordingMetadata(
        recipe=recipe if isinstance(recipe, str) else None,
        primary_entity_id=primary_entity_id if isinstance(primary_entity_id, str) else None,
        entities=_parse_metadata_entities(record.get("entities")),
        device_entities=_parse_metadata_entities(record.get("device_entities")),
        related_device_ids=_parse_strings(record.get("related_device_ids")),
    )


def _parse_strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


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
                "unique_id",
                "manufacturer",
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


def _parse_sample(record: dict[str, object], recording_id: int) -> RecordingSample:
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
    return RecordingSample(elapsed_seconds, power, entities, recording_id=recording_id)


def _parse_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError("expected a number")
    return float(value)
