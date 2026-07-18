from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from measure.controller.charging.const import BatteryLevelSourceType, ChargingControllerType, ChargingDeviceType


def charging_entity_domain(device_type: ChargingDeviceType) -> str:
    """Return the Home Assistant domain controlled for a charging device type."""

    return {
        ChargingDeviceType.VACUUM_ROBOT: "vacuum",
        ChargingDeviceType.LAWN_MOWER_ROBOT: "lawn_mower",
    }[device_type]


class _ChargingControllerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DummyChargingControllerSpec(_ChargingControllerSpec):
    type: Literal[ChargingControllerType.DUMMY] = ChargingControllerType.DUMMY


class HassChargingControllerSpec(_ChargingControllerSpec):
    type: Literal[ChargingControllerType.HASS] = ChargingControllerType.HASS
    entity_id: str = Field(pattern=r"^(vacuum|lawn_mower)\.[a-z0-9_]+$")
    battery_level_source_type: BatteryLevelSourceType = BatteryLevelSourceType.ATTRIBUTE
    battery_level_attribute: str | None = None
    battery_level_entity_id: str | None = Field(default=None, pattern=r"^sensor\.[a-z0-9_]+$")

    @model_validator(mode="after")
    def validate_battery_level_source(self) -> HassChargingControllerSpec:
        if self.battery_level_source_type == BatteryLevelSourceType.ENTITY and self.battery_level_entity_id is None:
            raise ValueError("battery_level_entity_id is required when the battery level source is an entity")
        return self


ChargingControllerSpec = Annotated[
    DummyChargingControllerSpec | HassChargingControllerSpec,
    Field(discriminator="type"),
]
