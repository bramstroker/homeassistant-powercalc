from __future__ import annotations

from typing import Any

from measure.controller.light.const import LutMode

from .controller import LightController, LightInfo


class DummyLightController(LightController):
    def change_light_state(
        self,
        lut_mode: LutMode,
        on: bool = True,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        return

    def get_light_info(self) -> LightInfo:
        return LightInfo("dummy")

    def has_effect_support(self) -> bool:
        return True

    def get_effect_list(self) -> list[str]:
        return ["A", "B", "C"]

    def close(self) -> None:
        return
