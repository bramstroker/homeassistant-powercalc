from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class RecorderProfileRecipe(StrEnum):
    GENERIC = "generic"
    VACUUM_ROBOT = "vacuum_robot"


class EntityRole(StrEnum):
    PRIMARY = "primary"
    BATTERY = "battery"
    TRACKED = "tracked"
    AVAILABLE = "available"
    DISABLED = "disabled"


@dataclass(frozen=True)
class RecordedEntity:
    """Metadata describing an entity included in a recording."""

    entity_id: str
    domain: str
    role: str  # Known roles use EntityRole; recordings may contain other role names.
    device_class: str | None = None
    integration: str | None = None
    translation_key: str | None = None
    device_id: str | None = None
    unit: str | None = None
    disabled_by: str | None = None
    has_live_state: bool | None = None
    unique_id: str | None = None
    manufacturer: str | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "entity_id": self.entity_id,
            "domain": self.domain,
            "role": self.role,
        }
        for key in (
            "device_class",
            "integration",
            "translation_key",
            "device_id",
            "unit",
            "disabled_by",
            "has_live_state",
            "unique_id",
            "manufacturer",
        ):
            item = getattr(self, key)
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True)
class RecordedEntityState:
    state: str
    attributes: Mapping[str, object]


@dataclass(frozen=True)
class RecordingSample:
    elapsed_seconds: float
    power: float
    entities: Mapping[str, RecordedEntityState]
    recording_id: int = 0


@dataclass(frozen=True)
class RecordingContext:
    """Recipe and device identity shared by recording and offline analysis."""

    recipe: RecorderProfileRecipe
    primary_entity_id: str
    device_type: str
    entities: list[RecordedEntity]
    device_entities: list[RecordedEntity] = field(default_factory=list)
    #: Devices besides the primary's whose entities PowerCalc profiles can reference, such as a vacuum dock.
    related_device_ids: list[str] = field(default_factory=list)

    def build_metadata_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_type": "metadata",
            "format_version": 1,
            "recipe": self.recipe,
            "primary_entity_id": self.primary_entity_id,
            "entities": [entity.to_dict() for entity in self.entities],
        }
        if self.device_entities:
            record["device_entities"] = [entity.to_dict() for entity in self.device_entities]
        if self.related_device_ids:
            record["related_device_ids"] = list(self.related_device_ids)
        return record


@dataclass(frozen=True)
class RecordingMetadata:
    """Parsed header; unknown recipe names remain readable for compatibility checks."""

    recipe: str | None
    primary_entity_id: str | None
    entities: list[RecordedEntity] = field(default_factory=list)
    device_entities: list[RecordedEntity] = field(default_factory=list)
    related_device_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecordingDataset:
    samples: list[RecordingSample]
    metadata: RecordingMetadata | None = None


@dataclass(frozen=True)
class LoadedRecording:
    dataset: RecordingDataset
    warnings: list[str] = field(default_factory=list)
