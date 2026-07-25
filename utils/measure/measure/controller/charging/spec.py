from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from measure.controller.charging.const import ChargingControllerType, ChargingDeviceType
from measure.controller.spec import BaseControllerSpec


def charging_entity_domain(device_type: ChargingDeviceType) -> str:
    """Return the Home Assistant domain controlled for a charging device type."""

    return {
        ChargingDeviceType.VACUUM_ROBOT: "vacuum",
        ChargingDeviceType.LAWN_MOWER_ROBOT: "lawn_mower",
    }[device_type]


class DummyChargingControllerSpec(BaseControllerSpec):
    type: Literal[ChargingControllerType.DUMMY] = ChargingControllerType.DUMMY


class HassChargingControllerSpec(BaseControllerSpec):
    type: Literal[ChargingControllerType.HASS] = ChargingControllerType.HASS
    entity_id: str = Field(pattern=r"^(vacuum|lawn_mower)\.[a-z0-9_]+$")


ChargingControllerSpec = Annotated[
    DummyChargingControllerSpec | HassChargingControllerSpec,
    Field(discriminator="type"),
]
