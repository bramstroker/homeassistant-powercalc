from typing import Annotated, Literal

from pydantic import Field, field_validator

from measure.controller.spec import BaseControllerSpec

SWITCH_ENTITY_PATTERN = r"^switch\.[a-z0-9_]+$"


class HassSwitchControllerSpec(BaseControllerSpec):
    type: Literal["hass"] = "hass"
    entity_id: str = Field(pattern=SWITCH_ENTITY_PATTERN)

    @property
    def entity_ids(self) -> list[str]:
        return [self.entity_id]


class HassMultiSwitchControllerSpec(BaseControllerSpec):
    type: Literal["hass_multi"] = "hass_multi"
    entity_ids: list[Annotated[str, Field(pattern=SWITCH_ENTITY_PATTERN)]] = Field(min_length=2, max_length=16)

    @field_validator("entity_ids")
    @classmethod
    def validate_unique_entity_ids(cls, entity_ids: list[str]) -> list[str]:
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("Switch entity IDs must be unique")
        return entity_ids


SwitchControllerSpec = Annotated[
    HassSwitchControllerSpec | HassMultiSwitchControllerSpec,
    Field(discriminator="type"),
]
