from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from measure.powermeter.const import PowerMeterType
from measure.request import POWER_ENTITY_PATTERN


class AppSettings(BaseModel):
    """Persistent, user-configurable defaults reused when starting new measurement sessions.

    Unknown keys are ignored so settings files written by other app versions keep loading.
    """

    model_config = ConfigDict(extra="ignore")

    default_power_entity_id: str | None = Field(default=None, pattern=POWER_ENTITY_PATTERN)
    default_measure_device: str | None = Field(default=None, max_length=200)
    power_meter: PowerMeterType = PowerMeterType.HASS
    shelly_ip: str | None = Field(default=None, max_length=255)
