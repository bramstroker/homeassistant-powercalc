from __future__ import annotations

from pydantic import BaseModel, ConfigDict

DUMMY_CONTROLLER_TYPE = "dummy"


class BaseControllerSpec(BaseModel):
    """Shared base for every controller spec.

    Each concrete spec narrows ``type`` to a Literal member of its own
    ``*ControllerType`` StrEnum. Those enums all use ``"dummy"`` for the
    synthetic controller, so ``is_dummy`` works across every domain without
    enumerating the concrete dummy classes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str

    @property
    def is_dummy(self) -> bool:
        return self.type == DUMMY_CONTROLLER_TYPE
