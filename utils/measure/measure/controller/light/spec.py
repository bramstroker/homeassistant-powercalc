from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from measure.controller.light.const import DEFAULT_LIGHT_TRANSITION_TIME, LightControllerType

LIGHT_ENTITY_PATTERN = r"^light\.[a-z0-9_]+$"


class _LightControllerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DummyLightControllerSpec(_LightControllerSpec):
    type: Literal[LightControllerType.DUMMY] = LightControllerType.DUMMY


class HassLightControllerSpec(_LightControllerSpec):
    type: Literal[LightControllerType.HASS] = LightControllerType.HASS
    entity_id: str = Field(pattern=LIGHT_ENTITY_PATTERN)
    transition_time: int = DEFAULT_LIGHT_TRANSITION_TIME


class HueLightControllerSpec(_LightControllerSpec):
    type: Literal[LightControllerType.HUE] = LightControllerType.HUE
    bridge_ip: str
    light: str


LightControllerSpec = Annotated[
    DummyLightControllerSpec | HassLightControllerSpec | HueLightControllerSpec,
    Field(discriminator="type"),
]
