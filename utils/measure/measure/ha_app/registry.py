from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from measure.const import MEASURE_TYPE_LABELS, MeasureType
from measure.controller.light.const import LutMode


class FieldControl(StrEnum):
    ENTITY = "entity"
    NUMBER = "number"
    TEXT = "text"
    BOOLEAN = "boolean"
    SELECT = "select"


@dataclass(frozen=True)
class FieldOption:
    value: str
    label: str


@dataclass(frozen=True)
class FormFieldDefinition:
    name: str
    label: str
    control: FieldControl
    required: bool = True
    entity_domains: tuple[str, ...] = ()
    options: tuple[FieldOption, ...] = ()
    default: str | int | bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None


@dataclass(frozen=True)
class MeasurementDefinition:
    kind: MeasureType
    description: str
    fields: tuple[FormFieldDefinition, ...] = ()
    supports_profile: bool = True
    supports_resume: bool = False

    @property
    def label(self) -> str:
        return MEASURE_TYPE_LABELS[self.kind]


def _entity(name: str, label: str, *domains: str) -> FormFieldDefinition:
    return FormFieldDefinition(name=name, label=label, control=FieldControl.ENTITY, entity_domains=domains)


POWER_FIELD = _entity("power_entity_id", "Power sensor", "sensor")

MEASUREMENT_REGISTRY: dict[MeasureType, MeasurementDefinition] = {
    MeasureType.LIGHT: MeasurementDefinition(
        kind=MeasureType.LIGHT,
        description="Build a lookup-table power profile for a light.",
        fields=(POWER_FIELD, _entity("light_entity_id", "Light", "light")),
        supports_resume=True,
    ),
    MeasureType.SPEAKER: MeasurementDefinition(
        kind=MeasureType.SPEAKER,
        description="Measure power across media-player volume levels.",
        fields=(
            POWER_FIELD,
            _entity("media_player_entity_id", "Media player", "media_player"),
            FormFieldDefinition(
                name="disable_streaming",
                label="Disable automatic pink-noise streaming",
                control=FieldControl.BOOLEAN,
                required=False,
                default=False,
            ),
        ),
    ),
    MeasureType.RECORDER: MeasurementDefinition(
        kind=MeasureType.RECORDER,
        description="Record live power readings to a CSV file until cancelled.",
        fields=(
            POWER_FIELD,
            FormFieldDefinition(
                name="export_filename",
                label="Export filename",
                control=FieldControl.TEXT,
                default="record.csv",
            ),
        ),
        supports_profile=False,
    ),
    MeasureType.AVERAGE: MeasurementDefinition(
        kind=MeasureType.AVERAGE,
        description="Measure average power for a fixed duration.",
        fields=(
            POWER_FIELD,
            FormFieldDefinition(
                name="duration",
                label="Duration (seconds)",
                control=FieldControl.NUMBER,
                default=60,
                minimum=1,
                maximum=86_400,
            ),
        ),
        supports_profile=False,
    ),
    MeasureType.CHARGING: MeasurementDefinition(
        kind=MeasureType.CHARGING,
        description="Measure charging power against battery level.",
        fields=(
            POWER_FIELD,
            FormFieldDefinition(
                name="charging_device_type",
                label="Charging device type",
                control=FieldControl.SELECT,
                options=(
                    FieldOption(value="vacuum_robot", label="Vacuum robot"),
                    FieldOption(value="lawn_mower_robot", label="Lawn mower robot"),
                ),
            ),
            _entity("charging_entity_id", "Charging device", "vacuum", "lawn_mower"),
        ),
    ),
    MeasureType.FAN: MeasurementDefinition(
        kind=MeasureType.FAN,
        description="Measure fan power across percentage levels.",
        fields=(POWER_FIELD, _entity("fan_entity_id", "Fan", "fan")),
    ),
}


def measurement_definitions() -> tuple[MeasurementDefinition, ...]:
    return tuple(MEASUREMENT_REGISTRY.values())


def supported_light_modes() -> tuple[LutMode, ...]:
    return (LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT)
