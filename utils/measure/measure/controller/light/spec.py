from typing import Annotated, Literal

from pydantic import Field, field_validator

from measure.controller.light.const import DEFAULT_LIGHT_TRANSITION_TIME, LightControllerType
from measure.controller.spec import BaseControllerSpec

LIGHT_ENTITY_PATTERN = r"^light\.[a-z0-9_]+$"


class DummyLightControllerSpec(BaseControllerSpec):
    type: Literal[LightControllerType.DUMMY] = LightControllerType.DUMMY


class HassLightControllerSpec(BaseControllerSpec):
    type: Literal[LightControllerType.HASS] = LightControllerType.HASS
    entity_id: str = Field(pattern=LIGHT_ENTITY_PATTERN)
    transition_time: int = DEFAULT_LIGHT_TRANSITION_TIME

    @property
    def entity_ids(self) -> list[str]:
        """Lights this spec drives, so callers can treat single and multi specs alike."""
        return [self.entity_id]


class HassMultiLightControllerSpec(BaseControllerSpec):
    type: Literal["hass_multi"] = "hass_multi"
    entity_ids: list[Annotated[str, Field(pattern=LIGHT_ENTITY_PATTERN)]] = Field(min_length=2, max_length=100)
    transition_time: int = DEFAULT_LIGHT_TRANSITION_TIME

    @field_validator("entity_ids")
    @classmethod
    def validate_unique_entity_ids(cls, entity_ids: list[str]) -> list[str]:
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("Light entity IDs must be unique")
        return entity_ids


class HueLightControllerSpec(BaseControllerSpec):
    type: Literal[LightControllerType.HUE] = LightControllerType.HUE
    bridge_ip: str
    light: str


LightControllerSpec = Annotated[
    DummyLightControllerSpec | HassLightControllerSpec | HassMultiLightControllerSpec | HueLightControllerSpec,
    Field(discriminator="type"),
]
