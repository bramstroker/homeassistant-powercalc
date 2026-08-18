from collections.abc import Callable, Sequence
import time
from typing import Any

from homeassistant_api import State
from homeassistant_api.errors import HomeassistantAPIError

from measure.controller.errors import ApiConnectionError
from measure.controller.hass_controller import HassControllerBase
from measure.controller.light.capabilities import (
    common_effects,
    light_info_from_attributes,
    merge_light_infos,
    mired_to_kelvin,
)
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.home_assistant import HomeAssistantManager


class HassLightController(HassControllerBase, LightController):
    """Drive one or more Home Assistant lights as a single measurement target.

    Several identical lights can be measured together to lift a load that is too small
    to register on its own. They then report the capabilities they have in common.
    """

    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        transition_time: int,
        *,
        entity_ids: Sequence[str],
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if not entity_ids:
            raise ValueError("A light controller needs at least one entity")
        self._transition_time: int = transition_time
        self._wait = wait
        # Every light is addressed explicitly, so the base class' single entity_id does not apply.
        self.entity_ids = list(entity_ids)
        super().__init__(home_assistant)

    @property
    def service_target(self) -> str | list[str]:
        """Entity target for light services: one light stays a plain ID, several become a list."""
        return self.entity_ids[0] if len(self.entity_ids) == 1 else list(self.entity_ids)

    def change_light_state(
        self,
        lut_mode: LutMode,
        on: bool = True,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        try:
            if not on:
                self.client.trigger_service("light", "turn_off", entity_id=self.service_target)
                return

            if lut_mode == LutMode.HS:
                json = self.build_hs_json_body(kwargs["bri"], kwargs["hue"], kwargs["sat"])
            elif lut_mode == LutMode.COLOR_TEMP:
                json = self.build_ct_json_body(kwargs["bri"], kwargs["ct"])
            elif lut_mode == LutMode.EFFECT:
                json = self.build_effect_json_body(kwargs["bri"], kwargs["effect"])
            elif lut_mode == LutMode.WHITE:
                json = self.build_white_json_body(kwargs["bri"])
            else:
                json = self.build_bri_json_body(kwargs["bri"])

            self.client.trigger_service("light", "turn_on", **json)
        except (HomeassistantAPIError, OSError) as e:
            raise ApiConnectionError(f"Failed to change light state: {e}") from e
        self._wait(self._transition_time)

    def get_light_info(self) -> LightInfo:
        return merge_light_infos([light_info_from_attributes(state.attributes) for state in self._states()])

    def has_effect_support(self) -> bool:
        return True

    def get_effect_list(self) -> list[str]:
        return common_effects(
            [[str(effect) for effect in state.attributes.get("effect_list", [])] for state in self._states()],
        )

    def close(self) -> None:
        return

    def build_hs_json_body(self, bri: int, hue: int, sat: int) -> dict[str, Any]:
        return {
            "entity_id": self.service_target,
            "transition": self._transition_time,
            "brightness": bri,
            "hs_color": [hue / 65535 * 360, sat / 255 * 100],
        }

    def build_ct_json_body(self, bri: int, ct: int) -> dict[str, Any]:
        return {
            "entity_id": self.service_target,
            "transition": self._transition_time,
            "brightness": bri,
            "color_temp_kelvin": mired_to_kelvin(ct),
        }

    def build_bri_json_body(self, bri: int) -> dict[str, Any]:
        return {
            "entity_id": self.service_target,
            "transition": self._transition_time,
            "brightness": bri,
        }

    def build_effect_json_body(self, bri: int, effect: str) -> dict[str, Any]:
        return {
            "entity_id": self.service_target,
            "effect": effect,
            "brightness": bri,
        }

    def build_white_json_body(self, bri: int) -> dict[str, Any]:
        return {
            "entity_id": self.service_target,
            "white": bri,
        }

    def _states(self) -> list[State]:
        return [self.client.get_state(entity_id=entity_id) for entity_id in self.entity_ids]
