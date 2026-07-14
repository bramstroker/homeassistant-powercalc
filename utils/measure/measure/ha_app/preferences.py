from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from measure.powermeter.const import PowerMeterType
from measure.powermeter.spec import POWER_ENTITY_PATTERN


class AppPreferences(BaseModel):
    """Persisted defaults for new sessions, tolerant of unknown settings keys."""

    model_config = ConfigDict(extra="ignore")

    default_power_entity_id: str | None = Field(default=None, pattern=POWER_ENTITY_PATTERN)
    default_measure_device: str | None = Field(default=None, max_length=200)
    power_meter: PowerMeterType = PowerMeterType.HASS
    shelly_ip: str | None = Field(default=None, max_length=255)
