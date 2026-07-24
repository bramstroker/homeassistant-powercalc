from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from measure.controller.fan.const import FanControllerType
from measure.controller.spec import BaseControllerSpec


class DummyFanControllerSpec(BaseControllerSpec):
    type: Literal[FanControllerType.DUMMY] = FanControllerType.DUMMY


class HassFanControllerSpec(BaseControllerSpec):
    type: Literal[FanControllerType.HASS] = FanControllerType.HASS
    entity_id: str = Field(pattern=r"^fan\.[a-z0-9_]+$")


FanControllerSpec = Annotated[
    DummyFanControllerSpec | HassFanControllerSpec,
    Field(discriminator="type"),
]
