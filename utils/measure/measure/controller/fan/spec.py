from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from measure.controller.fan.const import FanControllerType


class _FanControllerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DummyFanControllerSpec(_FanControllerSpec):
    type: Literal[FanControllerType.DUMMY] = FanControllerType.DUMMY


class HassFanControllerSpec(_FanControllerSpec):
    type: Literal[FanControllerType.HASS] = FanControllerType.HASS
    entity_id: str = Field(pattern=r"^fan\.[a-z0-9_]+$")


FanControllerSpec = Annotated[
    DummyFanControllerSpec | HassFanControllerSpec,
    Field(discriminator="type"),
]
