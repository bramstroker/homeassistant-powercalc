from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from measure.controller.charging.const import BatteryLevelSourceType, ChargingControllerType


class _ChargingControllerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DummyChargingControllerSpec(_ChargingControllerSpec):
    type: Literal[ChargingControllerType.DUMMY] = ChargingControllerType.DUMMY


class HassChargingControllerSpec(_ChargingControllerSpec):
    type: Literal[ChargingControllerType.HASS] = ChargingControllerType.HASS
    entity_id: str = Field(pattern=r"^(vacuum|lawn_mower)\.[a-z0-9_]+$")
    battery_level_source_type: BatteryLevelSourceType = BatteryLevelSourceType.ATTRIBUTE
    battery_level_attribute: str | None = None
    battery_level_entity_id: str | None = None


ChargingControllerSpec = Annotated[
    DummyChargingControllerSpec | HassChargingControllerSpec,
    Field(discriminator="type"),
]
