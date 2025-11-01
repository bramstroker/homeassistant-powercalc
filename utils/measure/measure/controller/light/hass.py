from __future__ import annotations

import math
import time
from typing import Any

from homeassistant_api.errors import HomeassistantAPIError
import inquirer

from measure.const import QUESTION_ENTITY_ID
from measure.controller.errors import ApiConnectionError
from measure.controller.hass_controller import HassControllerBase
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightController, LightInfo


class HassLightController(HassControllerBase, LightController):
    def __init__(self, api_url: str, token: str, transition_time: int) -> None:
        self._transition_time: int = transition_time
        super().__init__(api_url, token)

    def change_light_state(
        self,
        lut_mode: LutMode,
        on: bool = True,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        if not on:
            self.client.trigger_service("light", "turn_off", entity_id=self.entity_id)
            return

        json = {
            LutMode.HS: self.build_hs_json_body,
            LutMode.COLOR_TEMP: self.build_ct_json_body,
            LutMode.BRIGHTNESS: self.build_bri_json_body,
            LutMode.EFFECT: self.build_effect_json_body,
            LutMode.WHITE: self.build_white_json_body,
        }.get(lut_mode, self.build_bri_json_body)(**kwargs)

        try:
            self.client.trigger_service("light", "turn_on", **json)
        except HomeassistantAPIError as e:
            raise ApiConnectionError(f"Failed to change light state: {e}") from e
        time.sleep(self._transition_time)

    def get_light_info(self) -> LightInfo:
        state = self.client.get_state(entity_id=self.entity_id)
        attrs = state.attributes
        min_mired = MIN_MIRED
        if "max_color_temp_kelvin" in attrs:
            min_mired = self.kelvin_to_mired(attrs.get("max_color_temp_kelvin"))
        max_mired = MAX_MIRED
        if "min_color_temp_kelvin" in attrs:
            max_mired = self.kelvin_to_mired(attrs.get("min_color_temp_kelvin"))
        return LightInfo("unknown", min_mired, max_mired)

    def get_questions(self) -> list[inquirer.questions.Question]:
        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the light entity",
                choices=self.get_domain_entity_list("light"),
            ),
        ]

    def has_effect_support(self) -> bool:
        return True

    def get_effect_list(self) -> list[str]:
        light_state = self.client.get_state(entity_id=self.entity_id)
        return light_state.attributes.get("effect_list", [])

    def process_answers(self, answers: dict[str, Any]) -> None:
        super().process_answers(answers)

    def build_hs_json_body(self, bri: int, hue: int, sat: int) -> dict:
        return {
            "entity_id": self.entity_id,
            "transition": self._transition_time,
            "brightness": bri,
            "hs_color": [hue / 65535 * 360, sat / 255 * 100],
        }

    def build_ct_json_body(self, bri: int, ct: int) -> dict:
        return {
            "entity_id": self.entity_id,
            "transition": self._transition_time,
            "brightness": bri,
            "color_temp_kelvin": self.mired_to_kelvin(ct),
        }

    def build_bri_json_body(self, bri: int) -> dict:
        return {
            "entity_id": self.entity_id,
            "transition": self._transition_time,
            "brightness": bri,
        }

    def build_effect_json_body(self, bri: int, effect: str) -> dict:
        return {
            "entity_id": self.entity_id,
            "effect": effect,
            "brightness": bri,
        }

    def build_white_json_body(self, bri: int) -> dict:
        return {
            "entity_id": self.entity_id,
            "white": bri,
        }

    @staticmethod
    def kelvin_to_mired(kelvin_temperature: float) -> int:
        """Convert degrees kelvin to mired shift."""
        return math.floor(1000000 / kelvin_temperature)

    @staticmethod
    def mired_to_kelvin(mired_temperature: float) -> int:
        """Convert absolute mired shift to degrees kelvin."""
        return math.floor(1000000 / mired_temperature)
