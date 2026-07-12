from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from measure.configuration import MeasurementSettings
from measure.const import MeasureType
from measure.controller.charging.const import ChargingControllerType
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.media.const import MediaControllerType
from measure.powermeter.const import PowerMeterType

LIGHT_ENTITY_PATTERN = r"^light\.[a-z0-9_]+$"
POWER_ENTITY_PATTERN = r"^sensor\.[a-z0-9_]+$"
VOLTAGE_ENTITY_PATTERN = r"^sensor\.[a-z0-9_]+$"


class ResumePolicy(StrEnum):
    NEW = "new"
    RESUME = "resume"
    OVERWRITE = "overwrite"


@dataclass(frozen=True)
class LightMeasurementRequest:
    model_id: str
    model_name: str
    measure_device: str
    light_entity_id: str
    power_entity_id: str | None
    voltage_entity_id: str | None = None
    modes: frozenset[LutMode] = field(default_factory=lambda: frozenset({LutMode.BRIGHTNESS}))
    generate_model_json: bool = True
    gzip: bool = True
    num_lights: int = 1
    resume_policy: ResumePolicy = ResumePolicy.NEW
    settings: MeasurementSettings = field(default_factory=MeasurementSettings)


@dataclass(frozen=True)
class MeasurementRunRequest:
    """Transport-neutral request used by every measurement runner."""

    measure_type: MeasureType
    model_id: str
    model_name: str
    measure_device: str
    answers: dict[str, object]
    generate_model_json: bool = False
    resume_policy: ResumePolicy = ResumePolicy.NEW
    settings: MeasurementSettings = field(default_factory=MeasurementSettings)


class LightMeasurementRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=200)
    measure_device: str = Field(min_length=1, max_length=200)
    light_entity_id: str = Field(pattern=LIGHT_ENTITY_PATTERN)
    power_entity_id: str | None = Field(default=None, pattern=POWER_ENTITY_PATTERN)
    voltage_entity_id: str | None = Field(default=None, pattern=VOLTAGE_ENTITY_PATTERN)
    modes: set[LutMode] = Field(default_factory=lambda: {LutMode.BRIGHTNESS}, min_length=1)
    generate_model: bool = True
    gzip: bool = True
    multiple_light_count: int = Field(default=1, ge=1, le=100)
    sleep_time: float = Field(default=2, ge=0, le=120)
    sample_count: int = Field(default=1, ge=1, le=100)
    brightness_step: int = Field(default=5, ge=1, le=100)
    hue_step: int = Field(default=10, ge=1, le=360)
    saturation_step: int = Field(default=10, ge=1, le=100)
    color_temp_step: int = Field(default=5, ge=1, le=100)
    resume_policy: ResumePolicy = ResumePolicy.NEW

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        value = value.strip()
        if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", value):
            raise ValueError("model_id contains unsafe characters")
        return value

    @field_validator("power_entity_id", "voltage_entity_id", mode="before")
    @classmethod
    def empty_entity_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("modes")
    @classmethod
    def validate_modes(cls, value: set[LutMode]) -> set[LutMode]:
        unsupported = value - {LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT}
        if unsupported:
            raise ValueError(f"Unsupported app measurement modes: {', '.join(sorted(unsupported))}")
        return value

    def to_domain(self) -> LightMeasurementRequest:
        return LightMeasurementRequest(
            model_id=self.model_id,
            model_name=self.product_name.strip(),
            measure_device=self.measure_device.strip(),
            light_entity_id=self.light_entity_id,
            power_entity_id=self.power_entity_id,
            voltage_entity_id=self.voltage_entity_id,
            modes=frozenset(self.modes),
            generate_model_json=self.generate_model,
            gzip=self.gzip,
            num_lights=self.multiple_light_count,
            resume_policy=self.resume_policy,
            settings=MeasurementSettings(
                sleep_time=round(self.sleep_time),
                sample_count=self.sample_count,
                brightness_step=self.brightness_step,
                hue_step=self.hue_step,
                saturation_step=self.saturation_step,
                color_temp_step=self.color_temp_step,
            ),
        )


class MeasurementRunRequestModel(BaseModel):
    """Generic web request for a runner definition.

    The definition registry validates the mode-specific answer values before execution.
    """

    model_config = ConfigDict(extra="forbid")

    measure_type: MeasureType
    model_id: str = Field(default="measurement", min_length=1, max_length=120)
    product_name: str = Field(default="Measurement", min_length=1, max_length=200)
    measure_device: str = Field(default="", max_length=200)
    answers: dict[str, object] = Field(default_factory=dict)
    generate_model: bool = False
    sleep_time: float = Field(default=2, ge=0, le=120)
    sample_count: int = Field(default=1, ge=1, le=100)
    resume_policy: ResumePolicy = ResumePolicy.NEW

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return LightMeasurementRequestModel.validate_model_id(value)

    def to_domain(self) -> MeasurementRunRequest:
        return MeasurementRunRequest(
            measure_type=self.measure_type,
            model_id=self.model_id,
            model_name=self.product_name.strip(),
            measure_device=self.measure_device.strip(),
            answers=self.answers,
            generate_model_json=self.generate_model,
            resume_policy=self.resume_policy,
            settings=MeasurementSettings(sleep_time=round(self.sleep_time), sample_count=self.sample_count),
        )


class AppMeasureConfig:
    """Runtime config for the Home Assistant app, adapted from a request's settings.

    All tuning values come straight from ``request.settings`` (whose defaults live in
    ``MeasurementSettings``). The only app-specific logic is fixing the controllers to
    Home Assistant and mapping the request's user-facing step sizes onto the internal
    lookup-table step scale.
    """

    def __init__(
        self,
        request: LightMeasurementRequest | MeasurementRunRequest,
        hass_url: str,
        hass_token: str,
        power_meter: PowerMeterType = PowerMeterType.HASS,
    ) -> None:
        settings = request.settings
        self.selected_light_controller = LightControllerType.HASS
        self.selected_media_controller = MediaControllerType.HASS
        self.selected_fan_controller = FanControllerType.HASS
        self.selected_charging_controller = ChargingControllerType.HASS
        self.selected_power_meter = power_meter
        self.hass_url = hass_url
        self.hass_token = hass_token
        self.hass_call_update_entity_service = settings.call_update_entity
        self.light_transition_time = settings.light_transition_time
        self.min_brightness = settings.min_brightness
        self.max_brightness = settings.max_brightness
        self.min_sat = settings.min_sat
        self.max_sat = settings.max_sat
        self.min_hue = settings.min_hue
        self.max_hue = settings.max_hue
        # The app expresses steps as user-facing increments; map them to internal knobs.
        self.ct_bri_steps = settings.brightness_step
        self.ct_mired_steps = settings.color_temp_step
        self.bri_bri_steps = settings.brightness_step
        self.hs_bri_steps = max(1, round(settings.brightness_step / 100 * 255))
        self.hs_hue_steps = max(1, round(settings.hue_step / 360 * 65535))
        self.hs_sat_steps = max(1, round(settings.saturation_step / 100 * 255))
        self.effect_bri_steps = settings.effect_bri_steps
        self.measure_time_effect = settings.measure_time_effect
        self.measure_time_effect_min = settings.measure_time_effect_min
        self.measure_time_effect_convergence_window = settings.measure_time_effect_convergence_window
        self.measure_time_effect_convergence_abs = settings.measure_time_effect_convergence_abs
        self.measure_time_effect_convergence_rel = settings.measure_time_effect_convergence_rel
        self.sleep_initial = settings.sleep_initial
        self.sleep_standby = settings.sleep_standby
        self.sleep_time = settings.sleep_time
        self.sleep_time_sample = settings.sleep_time_sample
        self.sleep_time_hue = settings.sleep_time_hue
        self.sleep_time_sat = settings.sleep_time_sat
        self.sleep_time_ct = settings.sleep_time_ct
        self.sleep_time_effect_change = settings.sleep_time_effect_change
        self.sleep_time_nudge = settings.sleep_time_nudge
        self.pulse_time_nudge = settings.pulse_time_nudge
        self.sample_count = settings.sample_count
        self.max_retries = settings.max_retries
        self.max_nudges = settings.max_nudges
        self.resume = request.resume_policy == ResumePolicy.RESUME
        self.prompt_resume = False
        self.csv_add_datetime_column = settings.csv_add_datetime_column
