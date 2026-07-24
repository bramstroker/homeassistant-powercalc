from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from measure.controller.media.const import MediaControllerType
from measure.controller.spec import BaseControllerSpec


class DummyMediaControllerSpec(BaseControllerSpec):
    type: Literal[MediaControllerType.DUMMY] = MediaControllerType.DUMMY


class HassMediaControllerSpec(BaseControllerSpec):
    type: Literal[MediaControllerType.HASS] = MediaControllerType.HASS
    entity_id: str = Field(pattern=r"^media_player\.[a-z0-9_]+$")


MediaControllerSpec = Annotated[
    DummyMediaControllerSpec | HassMediaControllerSpec,
    Field(discriminator="type"),
]
