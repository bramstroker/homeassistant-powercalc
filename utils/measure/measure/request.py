from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from measure.const import PARAMETER_LIMITS, MeasureType
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.charging.spec import ChargingControllerSpec
from measure.controller.fan.spec import FanControllerSpec
from measure.controller.light.const import LutMode
from measure.controller.light.spec import LightControllerSpec
from measure.controller.media.spec import MediaControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec, PowerMeterSpec
from measure.runner.const import DEFAULT_EXPORT_FILENAME
from measure.tuning import MeasurementParameters


class ResumePolicy(StrEnum):
    NEW = "new"
    RESUME = "resume"
    OVERWRITE = "overwrite"


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


def _validate_parameter_limits(parameters: MeasurementParameters, names: Iterable[str]) -> None:
    for name in names:
        minimum, maximum = PARAMETER_LIMITS[name]
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
    resume_policy: ResumePolicy = ResumePolicy.NEW
    dummy_load: DummyLoadRequest | None = None

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        value = value.strip()
        if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", value):
            raise ValueError("model_id contains unsafe characters")
        return value

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
    def model_name(self) -> str:
        return self.product_name.strip()

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

    @field_validator("parameters")
    @classmethod
    def validate_light_parameters(cls, value: MeasurementParameters) -> MeasurementParameters:
        _validate_parameter_limits(value, _LIGHT_PARAMETER_FIELDS)
        if value.measure_time_effect_min > value.measure_time_effect:
            raise ValueError("measure_time_effect_min must not exceed measure_time_effect")
        return value


class AverageMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.AVERAGE] = MeasureType.AVERAGE
    duration: int = Field(default=60, ge=1, le=86_400)


class RecorderMeasurementRequest(BaseMeasurementRequest):
    measure_type: Literal[MeasureType.RECORDER] = MeasureType.RECORDER
    export_filename: str = Field(default=DEFAULT_EXPORT_FILENAME, min_length=1, max_length=200)

    @field_validator("export_filename")
    @classmethod
    def validate_export_filename(cls, value: str) -> str:
        return validate_export_filename(value)


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
