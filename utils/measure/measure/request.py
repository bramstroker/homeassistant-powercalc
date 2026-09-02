from collections.abc import Iterable
from enum import StrEnum
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from measure.const import MANUAL_PARAMETER_LIMIT_OVERRIDES, PARAMETER_LIMITS, MeasureType
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.charging.spec import ChargingControllerSpec
from measure.controller.fan.spec import FanControllerSpec
from measure.controller.light.const import LutMode
from measure.controller.light.spec import LightControllerSpec
from measure.controller.media.spec import MediaControllerSpec
from measure.controller.spec import BaseControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec, ManualPowerMeterSpec, PowerMeterSpec
from measure.runner.const import COMPLEX_PROFILE_EXPORT_FILENAME, DEFAULT_EXPORT_FILENAME
from measure.tuning import MeasurementParameters


class ResumePolicy(StrEnum):
    NEW = "new"
    RESUME = "resume"


class RecorderPurpose(StrEnum):
    PLAYBOOK = "playbook"
    COMPLEX_PROFILE = "complex_profile"


class RecorderProfileRecipe(StrEnum):
    GENERIC = "generic"
    VACUUM_ROBOT = "vacuum_robot"


class DummyLoadCalibrationRequest(BaseModel):
    """Request calibration of a physical resistive dummy load before measuring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["calibrate"] = "calibrate"
    description: str = Field(min_length=1, max_length=200)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("dummy-load description is required")
        return value


class DummyLoadReuseRequest(BaseModel):
    """Use a previously calibrated physical resistive dummy load."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["reuse"] = "reuse"
    description: str = Field(min_length=1, max_length=200)
    resistance: float = Field(gt=0)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("dummy-load description is required")
        return value


type DummyLoadRequest = Annotated[
    DummyLoadCalibrationRequest | DummyLoadReuseRequest,
    Field(discriminator="mode"),
]


_BASE_PARAMETER_FIELDS = ("sleep_time", "sample_count", "sleep_time_sample", "max_retries", "max_nudges")
_LIGHT_PARAMETER_FIELDS = (
    "min_brightness",
    "min_sat",
    "max_sat",
    "min_hue",
    "max_hue",
    "bri_bri_steps",
    "ct_bri_steps",
    "ct_mired_steps",
    "hs_bri_steps",
    "hs_hue_steps",
    "hs_sat_steps",
    "effect_bri_steps",
    "sleep_initial",
    "sleep_standby",
    "measure_time_effect",
    "measure_time_effect_min",
)


def _validate_parameter_limits(
    parameters: MeasurementParameters,
    names: Iterable[str],
    overrides: dict[str, tuple[float, float]] | None = None,
) -> None:
    for name in names:
        minimum, maximum = (overrides or {}).get(name, PARAMETER_LIMITS[name])
        number = getattr(parameters, name)
        if not minimum <= number <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")


class BaseMeasurementRequest(BaseModel):
    """Complete validated description of one measurement run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    measure_type: MeasureType
    model_id: str = Field(default="measurement", min_length=1, max_length=120)
    product_name: str = Field(default="Measurement", min_length=1, max_length=200)
    measure_device: str = Field(default="", max_length=200)
    power_meter: PowerMeterSpec
    parameters: MeasurementParameters = Field(default_factory=MeasurementParameters)
    generate_model: bool = False
    fast_test_mode: bool = False
    resume_policy: ResumePolicy = ResumePolicy.NEW
    dummy_load: DummyLoadRequest | None = None
    # Measure types that drive a device (light/speaker/charging/fan) narrow this to their
    # own required, discriminated controller spec; average/recorder leave it as None.
    controller: BaseControllerSpec | None = None

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        value = value.strip()
        if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", value):
            raise ValueError("model_id contains unsafe characters")
        return value

    @field_validator("product_name", "measure_device", mode="before")
    @classmethod
    def normalize_profile_metadata(cls, value: str) -> str:
        return value.strip()

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: MeasurementParameters) -> MeasurementParameters:
        _validate_parameter_limits(value, _BASE_PARAMETER_FIELDS)
        return value

    @model_validator(mode="after")
    def validate_dummy_load_power_meter(self) -> BaseMeasurementRequest:
        if self.dummy_load is not None and isinstance(self.power_meter, DummyPowerMeterSpec):
            raise ValueError("A resistive dummy load cannot be used with the synthetic test power meter")
        return self

    @property
    def controlled_entity_ids(self) -> tuple[str, ...]:
        """Home Assistant entities driven during the measurement, empty when the controller drives none."""
        entity_ids = getattr(self.controller, "entity_ids", None) or [getattr(self.controller, "entity_id", None)]
        return tuple(str(entity_id) for entity_id in entity_ids if entity_id)

    @property
    def model_name(self) -> str:
        return self.product_name

    @property
    def generate_model_json(self) -> bool:
        return self.generate_model


class LightMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.LIGHT] = MeasureType.LIGHT
    model_id: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=200)
    measure_device: str = Field(min_length=1, max_length=200)
    controller: LightControllerSpec
    modes: set[LutMode] = Field(default_factory=lambda: {LutMode.BRIGHTNESS}, min_length=1)
    generate_model: bool = True
    gzip: bool = True
    multiple_light_count: int = Field(default=1, ge=1, le=100)

    @field_validator("modes")
    @classmethod
    def validate_modes(cls, value: set[LutMode]) -> set[LutMode]:
        unsupported = value - {LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT}
        if unsupported:
            raise ValueError(f"Unsupported measurement modes: {', '.join(sorted(unsupported))}")
        return value

    @model_validator(mode="after")
    def validate_light_parameters(self) -> LightMeasurementRequest:
        # Manual meters use a coarser fixed ct grid than the automated density guard allows.
        overrides = MANUAL_PARAMETER_LIMIT_OVERRIDES if isinstance(self.power_meter, ManualPowerMeterSpec) else None
        value = self.parameters
        _validate_parameter_limits(value, _LIGHT_PARAMETER_FIELDS, overrides)
        if value.measure_time_effect_min > value.measure_time_effect:
            raise ValueError("measure_time_effect_min must not exceed measure_time_effect")
        if value.min_sat > value.max_sat:
            raise ValueError("min_sat must not exceed max_sat")
        if value.min_hue > value.max_hue:
            raise ValueError("min_hue must not exceed max_hue")
        return self


class AverageMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.AVERAGE] = MeasureType.AVERAGE
    controller: None = None
    duration: int = Field(default=60, ge=1, le=86_400)


class RecorderMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.RECORDER] = MeasureType.RECORDER
    controller: None = None
    recorder_purpose: RecorderPurpose = RecorderPurpose.PLAYBOOK
    profile_recipe: RecorderProfileRecipe | None = None
    tracked_entity_ids: tuple[str, ...] = Field(default=(), max_length=100)
    vacuum_entity_id: str | None = None
    battery_entity_id: str | None = None
    additional_entity_ids: tuple[str, ...] = Field(default=(), max_length=100)
    export_filename: str = Field(default=DEFAULT_EXPORT_FILENAME, min_length=1, max_length=200)

    @property
    def generate_model_json(self) -> bool:
        """Recorder model generation is handled by the analyser after capture."""

        return False

    @model_validator(mode="before")
    @classmethod
    def select_export_filename(cls, data: object) -> object:
        """Use the fixed filename for the selected recorder output format."""

        if not isinstance(data, dict):
            return data
        filename = (
            COMPLEX_PROFILE_EXPORT_FILENAME
            if data.get("recorder_purpose") == RecorderPurpose.COMPLEX_PROFILE
            else DEFAULT_EXPORT_FILENAME
        )
        return data | {"export_filename": filename}

    @field_validator(
        "tracked_entity_ids",
        "additional_entity_ids",
        mode="after",
    )
    @classmethod
    def validate_entity_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_entity_id(value)
        return values

    @field_validator("vacuum_entity_id", "battery_entity_id", mode="after")
    @classmethod
    def validate_optional_entity_id(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_entity_id(value)
        return value

    @model_validator(mode="after")
    def validate_recorder_selection(self) -> RecorderMeasurementRequest:
        if self.recorder_purpose == RecorderPurpose.PLAYBOOK:
            if self._has_profile_selection():
                raise ValueError("Playbook recordings cannot include complex-profile entity selections")
            return self

        if self.profile_recipe is None:
            raise ValueError("profile_recipe is required for a complex-profile recording")
        if self.profile_recipe == RecorderProfileRecipe.GENERIC:
            self._validate_generic_selection()
        else:
            self._validate_vacuum_selection()

        entity_ids = self.recorded_entity_ids
        if len(entity_ids) > 100:
            raise ValueError("A recorder session can track at most 100 entities")
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("Recorder entity selections must be unique")
        return self

    def _has_profile_selection(self) -> bool:
        return bool(
            self.profile_recipe
            or self.tracked_entity_ids
            or self.vacuum_entity_id
            or self.battery_entity_id
            or self.additional_entity_ids
        )

    def _validate_generic_selection(self) -> None:
        if not self.tracked_entity_ids:
            raise ValueError("Select at least one entity for a generic complex-profile recording")
        if self.vacuum_entity_id or self.battery_entity_id or self.additional_entity_ids:
            raise ValueError("Generic recordings cannot include vacuum-recipe entity selections")

    def _validate_vacuum_selection(self) -> None:
        if self.tracked_entity_ids:
            raise ValueError("Vacuum recordings cannot include generic tracked entities")
        if self.vacuum_entity_id is None or self.battery_entity_id is None:
            raise ValueError("A vacuum and battery entity are required for a vacuum recording")
        if not self.vacuum_entity_id.startswith("vacuum."):
            raise ValueError("vacuum_entity_id must be a vacuum entity")
        if not self.battery_entity_id.startswith("sensor."):
            raise ValueError("battery_entity_id must be a sensor entity")

    @property
    def recorded_entity_ids(self) -> tuple[str, ...]:
        """Entities recorded in deterministic capture order."""

        if self.recorder_purpose == RecorderPurpose.PLAYBOOK:
            return ()
        if self.profile_recipe == RecorderProfileRecipe.GENERIC:
            return self.tracked_entity_ids
        return tuple(
            entity_id
            for entity_id in (self.vacuum_entity_id, self.battery_entity_id, *self.additional_entity_ids)
            if entity_id is not None
        )


class SpeakerMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.SPEAKER] = MeasureType.SPEAKER
    controller: MediaControllerSpec
    disable_streaming: bool = False
    generate_model: bool = True


class ChargingMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.CHARGING] = MeasureType.CHARGING
    controller: ChargingControllerSpec
    charging_device_type: ChargingDeviceType
    generate_model: bool = True


class FanMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.FAN] = MeasureType.FAN
    controller: FanControllerSpec
    generate_model: bool = True


type MeasurementRequest = (
    LightMeasurementRequest
    | AverageMeasurementRequest
    | RecorderMeasurementRequest
    | SpeakerMeasurementRequest
    | ChargingMeasurementRequest
    | FanMeasurementRequest
)

MeasurementRequestPayload = Annotated[MeasurementRequest, Field(discriminator="measure_type")]
_REQUEST_ADAPTER: TypeAdapter[MeasurementRequest] = TypeAdapter(MeasurementRequestPayload)


def parse_measurement_request(data: object) -> MeasurementRequest:
    """Validate persisted input using the measurement and adapter discriminators."""
    return _REQUEST_ADAPTER.validate_python(data)


def validate_export_filename(value: str) -> str:
    """Return a safe recorder basename which cannot escape its output directory."""
    value = value.strip()
    if value in {"", ".", ".."} or value != value.replace("\\", "/").rsplit("/", 1)[-1]:
        raise ValueError("export_filename must be a file name without directory components")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", value):
        raise ValueError("export_filename contains unsafe characters")
    return value


def _validate_entity_id(value: str) -> None:
    if not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value):
        raise ValueError(f"Invalid Home Assistant entity ID: {value}")
