from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from measure.powermeter.spec import PowerMeterSpec


class DummyLoadCalibration(BaseModel):
    """Reusable resistance measurement bound to one configured power meter."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1, max_length=200)
    resistance: float = Field(gt=0)
    calibrated_at: str
    power_meter_fingerprint: str


def power_meter_fingerprint(spec: PowerMeterSpec) -> str:
    """Return a stable, non-secret identity for calibration compatibility."""

    value = spec.model_dump_json(exclude_none=False)
    return hashlib.sha256(value.encode()).hexdigest()
