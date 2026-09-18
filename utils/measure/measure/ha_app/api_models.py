from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, Field

from measure.const import MeasureType
from measure.controller.light.const import LutMode
from measure.ha_app.light_probe import (
    LightLoadProbeResult,
)
from measure.ha_app.registry import FieldControl, FieldRole
from measure.ha_app.session import (
    SessionState,
)
from measure.home_assistant.entities import (
    EntityDescriptor,
)
from measure.powermeter.diagnostics import PowerMeterDiagnostic
from measure.request import MeasurementRequest
from measure.runner.interaction import OperatingPoint
from measure.visualization import PlotSpec


class ErrorResponse(BaseModel):
    code: str
    message: str
    field: str | None = None
    help_url: str | None = None
    help_label: str | None = None


ERROR_RESPONSE = {"model": ErrorResponse}


MeasurementRequestPayload = Annotated[MeasurementRequest, Body(discriminator="measure_type")]


class PreflightResponse(BaseModel):
    valid: bool
    warnings: list[str]
    estimated_variations: int | None = None
    estimated_duration_seconds: int | None = None
    supported_modes: list[LutMode] | None = None
    power_meter_diagnostic: PowerMeterDiagnostic | None = None
    battery_level_entity_id: str | None = None
    battery_level_attribute: str | None = None
    light_load_probe: LightLoadProbeResult | None = None


class EntityCatalogResponse(BaseModel):
    home_assistant_ready: bool
    lights: list[EntityDescriptor]
    powers: list[EntityDescriptor]
    voltages: list[EntityDescriptor]


class MeasureDeviceCatalogResponse(BaseModel):
    devices: list[str]


class ManufacturerCatalogResponse(BaseModel):
    manufacturers: list[str]


class DeviceSpecificationFieldResponse(BaseModel):
    name: str
    label: str
    description: str
    value_type: Literal["string", "number", "integer", "boolean"]
    collection: Literal["scalar", "array", "scalar_or_array"]
    options: list[str]


class DeviceSpecificationCatalogResponse(BaseModel):
    device_types: dict[str, list[DeviceSpecificationFieldResponse]]


class SessionFile(BaseModel):
    name: str
    size: int
    media_type: str


class SessionPlots(BaseModel):
    partial: bool
    plots: list[PlotSpec]
    warnings: list[str]


class SessionSummary(BaseModel):
    session_id: str
    state: SessionState
    created_at: str
    updated_at: str
    measure_type: MeasureType
    model_id: str
    product_name: str
    measure_device: str
    completed: int
    total: int
    percent: float
    can_resume: bool
    file_count: int
    size: int
    active: bool


class SessionProgressResponse(BaseModel):
    completed: int
    total: int
    skipped: int
    percent: float
    estimated_remaining_seconds: int | None


class CalibrationSampleResponse(BaseModel):
    power: float
    resistance: float
    voltage: float


class SessionSnapshotResponse(BaseModel):
    """Complete JSON contract returned by session endpoints and embedded in SSE events."""

    session_id: str
    state: SessionState
    created_at: str
    updated_at: str
    phase: str | None
    confirmation_message: str | None
    confirmation_action: str | None
    mode: str | None
    progress: SessionProgressResponse
    warnings: list[str]
    error: str | None
    summary: dict[str, str] | None
    operating_point: OperatingPoint | None
    calibration_sample: CalibrationSampleResponse | None
    entity_states: dict[str, str]
    can_analyse: bool
    request: MeasurementRequest


class SessionEventResponse(BaseModel):
    """Wire envelope shared by stored session events and SSE heartbeats."""

    sequence: int
    type: str
    data: dict[str, object]
    snapshot: SessionSnapshotResponse | None = None


class CapabilitiesResponse(BaseModel):
    runtime_version: str
    defaults: dict[str, int | float]
    limits: dict[str, dict[str, int | float]]
    developer_mode: bool = False
    fast_test_mode: bool = False


class FormFieldOption(BaseModel):
    value: str
    label: str
    entity_domain: str | None = None
    enables: list[str] = Field(default_factory=list)
    description: str = ""
    guidance: list[str] = Field(default_factory=list)


class FormField(BaseModel):
    name: str
    label: str
    control: FieldControl
    role: FieldRole = FieldRole.ATTRIBUTE
    narrowed_by: str | None = None
    required: bool = True
    entity_domains: list[str] = Field(default_factory=list)
    options: list[FormFieldOption] = Field(default_factory=list)
    default: str | int | bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    multiple: bool = False
    plural_label: str = ""
    derived_from: str | None = None
    hint: str = ""
    visible_when: dict[str, list[str]] = Field(default_factory=dict)
    all_entities: bool = False
    entity_device_classes: list[str] = Field(default_factory=list)
    related_to: str | None = None
    same_device_only: bool = False
    review: bool = False


class MeasureParameter(BaseModel):
    name: str
    label: str
    hint: str = ""
    step: str = "1"
    group: str = ""
    requires_multiple: str | None = None


class MeasureDefinition(BaseModel):
    measure_type: MeasureType
    label: str
    description: str
    icon: str
    confirmation_action: str | None
    confirmation_is_warning: bool = False
    model_id_example: str = ""
    product_name_example: str = ""
    fields: list[FormField]
    parameters: list[MeasureParameter] = Field(default_factory=list)
    supports_profile: bool
    supports_resume: bool
