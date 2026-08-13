from collections.abc import Callable
import time
from typing import Any

from homeassistant_api.errors import HomeassistantAPIError

from measure.controller.errors import ApiConnectionError
from measure.controller.hass_controller import HassControllerBase
from measure.controller.light.capabilities import light_info_from_attributes, mired_to_kelvin
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.home_assistant import HomeAssistantManager


class HassLightController(HassControllerBase, LightController):
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        transition_time: int,
        *,
        entity_id: str | None = None,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transition_time: int = transition_time
        self._wait = wait
        super().__init__(home_assistant, entity_id=entity_id)

    @property
    def target_entity_id(self) -> str | list[str] | None:
        return self.entity_id

    def change_light_state(
        self,
        lut_mode: LutMode,
        on: bool = True,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        if not on:
            self.client.trigger_service("light", "turn_off", entity_id=self.target_entity_id)
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

        try:
            self.client.trigger_service("light", "turn_on", **json)
        except HomeassistantAPIError as e:
            raise ApiConnectionError(f"Failed to change light state: {e}") from e
        self._wait(self._transition_time)

    def get_light_info(self) -> LightInfo:
        state = self.client.get_state(entity_id=self.entity_id)
        return light_info_from_attributes(state.attributes)

    def has_effect_support(self) -> bool:
        return True

    def get_effect_list(self) -> list[str]:
        light_state = self.client.get_state(entity_id=self.entity_id)
        return [str(effect) for effect in light_state.attributes.get("effect_list", [])]

    def close(self) -> None:
        return

    def build_hs_json_body(self, bri: int, hue: int, sat: int) -> dict[str, Any]:
        return {
            "entity_id": self.target_entity_id,
            "transition": self._transition_time,
            "brightness": bri,
            "hs_color": [hue / 65535 * 360, sat / 255 * 100],
        }

    def build_ct_json_body(self, bri: int, ct: int) -> dict[str, Any]:
        return {
            "entity_id": self.target_entity_id,
            "transition": self._transition_time,
            "brightness": bri,
            "color_temp_kelvin": mired_to_kelvin(ct),
        }

    def build_bri_json_body(self, bri: int) -> dict[str, Any]:
        return {
            "entity_id": self.target_entity_id,
            "transition": self._transition_time,
            "brightness": bri,
        }

    def build_effect_json_body(self, bri: int, effect: str) -> dict[str, Any]:
        return {
            "entity_id": self.target_entity_id,
            "effect": effect,
            "brightness": bri,
        }

    def build_white_json_body(self, bri: int) -> dict[str, Any]:
        return {
            "entity_id": self.target_entity_id,
            "white": bri,
        }


class HassMultiLightController(HassLightController):
    """Control multiple Home Assistant lights through one service target."""

    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        transition_time: int,
        *,
        entity_ids: list[str],
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self.entity_ids = tuple(entity_ids)
        super().__init__(home_assistant, transition_time, entity_id=entity_ids[0], wait=wait)

    @property
    def target_entity_id(self) -> str | list[str] | None:
        return list(self.entity_ids)

    def get_light_info(self) -> LightInfo:
        infos = [
            light_info_from_attributes(self.client.get_state(entity_id=entity_id).attributes)
            for entity_id in self.entity_ids
        ]
        return LightInfo(
            "unknown",
            min_mired=max(info.min_mired for info in infos),
            max_mired=min(info.max_mired for info in infos),
        )

    def get_effect_list(self) -> list[str]:
        effect_lists = [
            [str(effect) for effect in self.client.get_state(entity_id=entity_id).attributes.get("effect_list", [])]
            for entity_id in self.entity_ids
        ]
        return [effect for effect in effect_lists[0] if all(effect in other for other in effect_lists[1:])]
