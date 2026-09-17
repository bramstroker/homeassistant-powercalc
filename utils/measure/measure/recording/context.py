from collections.abc import Sequence
from typing import TYPE_CHECKING

from measure.recording.models import EntityRole, RecordedEntity, RecordingContext
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe

if TYPE_CHECKING:
    from measure.home_assistant.entities import EntityDescriptor


def recording_context_for(
    request: RecorderMeasurementRequest,
    descriptors: Sequence[EntityDescriptor] = (),
) -> RecordingContext:
    """Build the recording header from selected entities and optional registry metadata."""
    entity_ids = request.recorded_entity_ids
    if not entity_ids or request.profile_recipe is None:
        raise ValueError("A complex-profile recorder request is required for recording metadata")
    roles = dict.fromkeys(entity_ids, EntityRole.TRACKED)
    roles[entity_ids[0]] = EntityRole.PRIMARY
    if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT:
        roles[entity_ids[1]] = EntityRole.BATTERY
    by_id = {entity.entity_id: entity for entity in descriptors}

    primary = by_id.get(entity_ids[0])
    device_entities = [
        _recorded_entity(
            entity.entity_id, EntityRole.AVAILABLE if entity.disabled_by is None else EntityRole.DISABLED, entity
        )
        for entity in descriptors
        if primary is not None and primary.device_id is not None and entity.device_id == primary.device_id
    ]
    return RecordingContext(
        recipe=request.profile_recipe.value,
        primary_entity_id=entity_ids[0],
        device_type="vacuum_robot" if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT else "generic_iot",
        entities=[_recorded_entity(entity_id, roles[entity_id], by_id.get(entity_id)) for entity_id in entity_ids],
        device_entities=device_entities,
    )


def _recorded_entity(entity_id: str, role: EntityRole, descriptor: EntityDescriptor | None) -> RecordedEntity:
    """Copy registry metadata, or retain just the identity when no descriptor exists."""
    if descriptor is None:
        return RecordedEntity(entity_id, entity_id.partition(".")[0], role)
    return RecordedEntity(
        entity_id=entity_id,
        domain=descriptor.domain,
        role=role,
        device_class=descriptor.device_class,
        integration=descriptor.integration,
        translation_key=descriptor.translation_key,
        device_id=descriptor.device_id,
        unit=descriptor.unit,
        disabled_by=descriptor.disabled_by,
        has_live_state=descriptor.has_live_state,
    )
