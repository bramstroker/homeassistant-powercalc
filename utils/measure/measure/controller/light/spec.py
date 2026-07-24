from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from measure.controller.light.const import DEFAULT_LIGHT_TRANSITION_TIME, LightControllerType
from measure.controller.spec import BaseControllerSpec

LIGHT_ENTITY_PATTERN = r"^light\.[a-z0-9_]+$"


class DummyLightControllerSpec(BaseControllerSpec):
    type: Literal[LightControllerType.DUMMY] = LightControllerType.DUMMY


class HassLightControllerSpec(BaseControllerSpec):
    type: Literal[LightControllerType.HASS] = LightControllerType.HASS
    entity_id: str = Field(pattern=LIGHT_ENTITY_PATTERN)
    transition_time: int = DEFAULT_LIGHT_TRANSITION_TIME


class HueLightControllerSpec(BaseControllerSpec):
    type: Literal[LightControllerType.HUE] = LightControllerType.HUE
    bridge_ip: str
    light: str


LightControllerSpec = Annotated[
    DummyLightControllerSpec | HassLightControllerSpec | HueLightControllerSpec,
    Field(discriminator="type"),
]
