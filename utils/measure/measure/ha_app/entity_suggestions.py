"""Enrich the recorder's entity catalogue with defaults from the analyser."""

from measure.analyser.vacuum_signals import suggest_recording_entities
from measure.home_assistant.entities import EntityCatalogSnapshot, EntityDescriptor
from measure.recording.context import build_recorded_entity
from measure.recording.models import EntityRole, RecorderProfileRecipe, RecordingContext


def add_recording_suggestions(snapshot: EntityCatalogSnapshot) -> list[EntityDescriptor]:
    entities = snapshot.get_all()
    inventory = [build_recorded_entity(entity.entity_id, EntityRole.AVAILABLE, entity) for entity in entities]
    result: list[EntityDescriptor] = []
    for entity in entities:
        if entity.domain != "vacuum" or entity.device_id is None:
            result.append(entity)
            continue
        related = list(snapshot.related_device_ids.get(entity.device_id, []))
        device_ids = {entity.device_id, *related}
        device_entities = [item for item in inventory if item.device_id in device_ids]
        context = RecordingContext(
            recipe=RecorderProfileRecipe.VACUUM_ROBOT,
            primary_entity_id=entity.entity_id,
            device_type="vacuum_robot",
            entities=device_entities,
            device_entities=device_entities,
            related_device_ids=related,
        )
        suggestions = suggest_recording_entities(context)
        result.append(
            entity.model_copy(
                update={
                    "suggested_recording_entity_ids": suggestions.selected,
                    "disabled_recording_entity_ids": suggestions.disabled,
                }
            )
        )
    return result
