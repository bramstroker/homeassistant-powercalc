from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

POWER_ENTITY_PATTERN = r"^sensor\.[a-z0-9_]+$"


class AppSettings(BaseModel):
    """Persistent, user-configurable defaults reused when starting new measurement sessions.

    Unknown keys are ignored so settings files written by other app versions keep loading.
    """

    model_config = ConfigDict(extra="ignore")

    default_power_entity_id: str | None = Field(default=None, pattern=POWER_ENTITY_PATTERN)
