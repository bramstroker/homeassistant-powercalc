from __future__ import annotations

from typing import Any

import inquirer
from homeassistant_api import Client, HomeassistantAPIError

from .const import MAX_MIRED, MIN_MIRED, ColorMode
from .controller import LightController, LightInfo
from .errors import LightControllerError


class HassLightController(LightController):
    def __init__(self, api_url: str, token: str) -> None:
        self._entity_id: str | None = None
        self._model_id: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
            self.client.get_config()
        except HomeassistantAPIError as e:
            raise LightControllerError(f"Failed to connect to HA API: {e}")

    def change_light_state(self, color_mode: str, on: bool = True, **kwargs) -> None:
        if not on:
            self.client.trigger_service("light", "turn_off", entity_id=self._entity_id)
            return

        if color_mode == ColorMode.HS:
            json = self.build_hs_json_body(**kwargs)
        elif color_mode == ColorMode.COLOR_TEMP:
            json = self.build_ct_json_body(**kwargs)
        else:
            json = self.build_bri_json_body(**kwargs)

        self.client.trigger_service("light", "turn_on", **json)

    def get_light_info(self) -> LightInfo:
        state = self.client.get_state(entity_id=self._entity_id)
        min_mired = state.attributes.get("min_mireds") or MIN_MIRED
        max_mired = state.attributes.get("max_mireds") or MAX_MIRED
        return LightInfo(self._model_id, min_mired, max_mired)

    def get_questions(self) -> list[inquirer.questions.Question]:
        entities = self.client.get_entities()
        lights = entities["light"].entities.values()
        light_list = sorted([entity.entity_id for entity in lights])

        return [
            inquirer.List(
                name="light_entity_id",
                message="Select the light",
                choices=light_list,
            ),
            inquirer.Text(
                name="light_model_id",
                message="What model is your light? Ex: LED1837R5",
                validate=lambda _, x: len(x) > 0,
            ),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        self._entity_id = answers["light_entity_id"]
        self._model_id = answers["light_model_id"]

    def build_hs_json_body(self, bri: int, hue: int, sat: int) -> dict:
        return {
            "entity_id": self._entity_id,
            "transition": 0,
            "brightness": bri,
            "hs_color": [hue / 65535 * 360, sat / 255 * 100],
        }

    def build_ct_json_body(self, bri: int, ct: int) -> dict:
        return {
            "entity_id": self._entity_id,
            "transition": 0,
            "brightness": bri,
            "color_temp": ct,
        }

    def build_bri_json_body(self, bri: int) -> dict:
        return {"entity_id": self._entity_id, "transition": 0, "brightness": bri}
