from __future__ import annotations

import math
import time
from typing import Any

import inquirer
from homeassistant_api import Client, HomeassistantAPIError

from measure.const import QUESTION_ENTITY_ID, QUESTION_MODEL_ID
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, ColorMode
from measure.controller.light.controller import LightController, LightInfo
from measure.controller.light.errors import LightControllerError


class HassLightController(LightController):
    def __init__(self, api_url: str, token: str, transition_time: int) -> None:
        self._entity_id: str | None = None
        self._model_id: str | None = None
        self._transition_time: int = transition_time
        try:
            self.client = Client(api_url, token, cache_session=False)
            self.client.get_config()
        except HomeassistantAPIError as e:
            raise LightControllerError(f"Failed to connect to HA API: {e}") from e

    def change_light_state(
        self,
        color_mode: str,
        on: bool = True,
        **kwargs,  # noqa: ANN003
    ) -> None:
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
        time.sleep(self._transition_time)

    def get_light_info(self) -> LightInfo:
        state = self.client.get_state(entity_id=self._entity_id)
        attrs = state.attributes
        min_mired = self.kelvin_to_mired(attrs.get("max_color_temp_kelvin")) or MIN_MIRED
        max_mired = self.kelvin_to_mired(attrs.get("min_color_temp_kelvin")) or MAX_MIRED
        return LightInfo(self._model_id, min_mired, max_mired)

    def get_questions(self) -> list[inquirer.questions.Question]:
        entities = self.client.get_entities()
        lights = entities["light"].entities.values()
        light_list = sorted([entity.entity_id for entity in lights])

        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the light entity",
                choices=light_list,
            ),
            inquirer.Text(
                name=QUESTION_MODEL_ID,
                message="What model is your light? Ex: LED1837R5",
                validate=lambda _, x: len(x) > 0,
            ),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        self._entity_id = answers[QUESTION_ENTITY_ID]
        self._model_id = answers[QUESTION_MODEL_ID]

    def build_hs_json_body(self, bri: int, hue: int, sat: int) -> dict:
        return {
            "entity_id": self._entity_id,
            "transition": self._transition_time,
            "brightness": bri,
            "hs_color": [hue / 65535 * 360, sat / 255 * 100],
        }

    def build_ct_json_body(self, bri: int, ct: int) -> dict:
        return {
            "entity_id": self._entity_id,
            "transition": self._transition_time,
            "brightness": bri,
            "color_temp": ct,
        }

    def build_bri_json_body(self, bri: int) -> dict:
        return {"entity_id": self._entity_id, "transition": self._transition_time, "brightness": bri}

    @staticmethod
    def kelvin_to_mired(kelvin_temperature: float) -> int:
        """Convert degrees kelvin to mired shift."""
        return math.floor(1000000 / kelvin_temperature)
