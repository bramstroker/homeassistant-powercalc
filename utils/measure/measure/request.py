from __future__ import annotations

from enum import StrEnum
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from measure.const import (
    MEASUREMENT_SAMPLE_COUNT_MAX,
    MEASUREMENT_SAMPLE_COUNT_MIN,
    MEASUREMENT_SLEEP_TIME_MAX,
    MEASUREMENT_SLEEP_TIME_MIN,
    MeasureType,
)
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.charging.spec import ChargingControllerSpec
from measure.controller.fan.spec import FanControllerSpec
from measure.controller.light.const import LutMode
from measure.controller.light.spec import LightControllerSpec
from measure.controller.media.spec import MediaControllerSpec
from measure.powermeter.spec import PowerMeterSpec
from measure.runner.const import DEFAULT_EXPORT_FILENAME
from measure.tuning import MeasurementParameters


class ResumePolicy(StrEnum):
    NEW = "new"
    RESUME = "resume"
    OVERWRITE = "overwrite"


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
        if not MEASUREMENT_SLEEP_TIME_MIN <= value.sleep_time <= MEASUREMENT_SLEEP_TIME_MAX:
            raise ValueError(
                f"sleep_time must be between {MEASUREMENT_SLEEP_TIME_MIN} and {MEASUREMENT_SLEEP_TIME_MAX}",
            )
        if not MEASUREMENT_SAMPLE_COUNT_MIN <= value.sample_count <= MEASUREMENT_SAMPLE_COUNT_MAX:
            raise ValueError(
                f"sample_count must be between {MEASUREMENT_SAMPLE_COUNT_MIN} and {MEASUREMENT_SAMPLE_COUNT_MAX}",
            )
        return value

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
        for name, minimum, maximum in (
            ("brightness_step", 1, 100),
            ("hue_step", 1, 360),
            ("saturation_step", 1, 100),
            ("color_temp_step", 1, 100),
        ):
            number = getattr(value, name)
            if not minimum <= number <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
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
