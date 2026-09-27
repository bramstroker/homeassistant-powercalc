"""Resolve recorded entities to portable profile placeholders."""

from collections.abc import Callable, Sequence
import re

from measure.recording.models import RecordedEntity, RecordingContext


def resolve_portable_entity(
    entity_id: str, context: RecordingContext, *, unique_id_suffix: str | None = None
) -> str | None:
    """Map a recorded entity ID to a profile placeholder reusable in other HA installations.

    Use [[entity]] for the vacuum, otherwise a translation key or supported battery
    device class that PowerCalc resolves to exactly this entity. An explicitly
    supplied semantic suffix can identify entities on the primary device and integration.
    """
    if entity_id == context.primary_entity_id:
        return "[[entity]]"
    entity = next((entity for entity in context.entities if entity.entity_id == entity_id), None)
    primary = next((entity for entity in context.entities if entity.entity_id == context.primary_entity_id), None)
    if entity is None or primary is None or not primary.device_id or not entity.device_id:
        return None
    inventory = context.device_entities or context.entities
    source_entities = [item for item in inventory if item.device_id == primary.device_id]
    if entity.device_id == primary.device_id:
        candidates: list[RecordedEntity] = source_entities
        shadowing: list[RecordedEntity] = []
    elif entity.device_id in context.related_device_ids:
        # PowerCalc only searches related devices, such as a dock, when the vacuum's
        # own device has no match, and then requires one match across all of them.
        candidates = [item for item in inventory if item.device_id in context.related_device_ids]
        shadowing = source_entities
    else:
        return None

    key = entity.translation_key
    if key and _is_unique_match(candidates, shadowing, lambda item: item.translation_key == key):
        return f"[[entity_by_translation_key:{key}]]"
    device_class = entity.device_class
    if _has_portable_device_class(entity) and _is_unique_match(
        candidates, shadowing, lambda item: item.device_class == device_class
    ):
        return f"[[entity_by_device_class:{device_class}]]"
    if _has_unique_id_suffix_match(entity, primary, source_entities, unique_id_suffix):
        return f"[[entity_by_unique_id_suffix:{unique_id_suffix}]]"
    return None


def _has_unique_id_suffix_match(
    entity: RecordedEntity,
    primary: RecordedEntity,
    source_entities: Sequence[RecordedEntity],
    suffix: str | None,
) -> bool:
    """Allow a mapped suffix only when it identifies one entity on the vacuum's device."""
    if not suffix or re.fullmatch(r"[A-Za-z_]\w*", suffix) is None:
        return False
    if entity.device_id != primary.device_id or not primary.integration:
        return False
    if entity.integration != primary.integration or not entity.unique_id or not entity.unique_id.endswith(suffix):
        return False
    return _is_unique_match(
        source_entities,
        [],
        lambda item: (
            item.integration == primary.integration and item.unique_id is not None and item.unique_id.endswith(suffix)
        ),
    )


def _is_unique_match(
    candidates: Sequence[RecordedEntity],
    shadowing: Sequence[RecordedEntity],
    matches: Callable[[RecordedEntity], bool],
) -> bool:
    return not any(matches(item) for item in shadowing) and sum(matches(item) for item in candidates) == 1


def _has_portable_device_class(entity: RecordedEntity) -> bool:
    return (entity.domain == "sensor" and entity.device_class == "battery" and entity.unit == "%") or (
        entity.domain == "binary_sensor" and entity.device_class == "battery_charging"
    )
