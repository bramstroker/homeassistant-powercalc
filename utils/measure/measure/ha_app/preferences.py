from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from measure.const import PARAMETER_LIMITS
from measure.powermeter.const import PowerMeterType
from measure.powermeter.spec import POWER_ENTITY_PATTERN
from measure.tuning import MeasurementParameters

_DEFAULTS = MeasurementParameters()


def _bounded_field(name: str, default: float) -> Any:  # noqa: ANN401  # typed as Any so assignments match the field's type, like pydantic's Field()
    minimum, maximum = PARAMETER_LIMITS[name]
    return Field(default=default, ge=minimum, le=maximum)


class AppMeasurementDefaults(BaseModel):
    """Reusable measurement behavior copied into each new request."""

    model_config = ConfigDict(extra="ignore")

    sleep_time: float = _bounded_field("sleep_time", _DEFAULTS.sleep_time)
    sample_count: int = _bounded_field("sample_count", _DEFAULTS.sample_count)
    sleep_time_sample: int = _bounded_field("sleep_time_sample", _DEFAULTS.sleep_time_sample)
    max_retries: int = _bounded_field("max_retries", _DEFAULTS.max_retries)
    max_nudges: int = _bounded_field("max_nudges", _DEFAULTS.max_nudges)


class AppPreferences(BaseModel):
    """Persisted defaults for new sessions, tolerant of unknown settings keys."""

    model_config = ConfigDict(extra="ignore")

    default_power_entity_id: str | None = Field(default=None, pattern=POWER_ENTITY_PATTERN)
    default_measure_device: str | None = Field(default=None, max_length=200)
    power_meter: PowerMeterType = PowerMeterType.HASS
    shelly_ip: str | None = Field(default=None, max_length=255)
    fast_test_mode: bool = False
    measurement_defaults: AppMeasurementDefaults = Field(default_factory=AppMeasurementDefaults)
