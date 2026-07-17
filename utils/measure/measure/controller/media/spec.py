from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from measure.controller.media.const import MediaControllerType


class _MediaControllerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DummyMediaControllerSpec(_MediaControllerSpec):
    type: Literal[MediaControllerType.DUMMY] = MediaControllerType.DUMMY


class HassMediaControllerSpec(_MediaControllerSpec):
    type: Literal[MediaControllerType.HASS] = MediaControllerType.HASS
    entity_id: str = Field(pattern=r"^media_player\.[a-z0-9_]+$")


MediaControllerSpec = Annotated[
    DummyMediaControllerSpec | HassMediaControllerSpec,
    Field(discriminator="type"),
]
