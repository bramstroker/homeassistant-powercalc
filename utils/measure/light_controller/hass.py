from __future__ import annotations

import requests

from .const import MODE_COLOR_TEMP, MODE_HS
from .controller import LightController, LightInfo
from .errors import LightControllerError

NAME = "hass"

TURN_ON_ENDPOINT = "/services/light/turn_on"
TURN_OFF_ENDPOINT = "/services/light/turn_off"


class HassLightController(LightController):
    def __init__(self, api_url: str, token: str):
        self._api_url = api_url
        self._auth_header = {"Authorization": "Bearer " + token}

    def change_light_state(self, color_mode: str, on: bool = True, **kwargs):
        if on == False:
            self.call_ha_service(TURN_OFF_ENDPOINT, {"entity_id": self._entity_id})
            return

        if color_mode == MODE_HS:
            json = self.build_hs_json_body(**kwargs)
        elif color_mode == MODE_COLOR_TEMP:
            json = self.build_ct_json_body(**kwargs)
        else:
            json = self.build_bri_json_body(**kwargs)

        self.call_ha_service(TURN_ON_ENDPOINT, json)

    def call_ha_service(self, endpoint: str, json: dict, retry_count=0):
        resp = requests.post(
            self._api_url + endpoint, json=json, headers=self._auth_header
        )
        if resp.status_code != 200 and resp.status_code != 201:
            if retry_count < 3:
                retry_count = retry_count + 1
                self.call_ha_service(endpoint, json, retry_count)
            raise LightControllerError(
                "Tried to call HA api 3 times, but response was invalid", resp.content
            )

    def get_light_info(self) -> LightInfo:
        state = self.get_entity_state(self._entity_id)
        min_mired = state.get("attributes").get("min_mireds")
        max_mired = state.get("attributes").get("max_mireds")
        return LightInfo(self._model_id, min_mired, max_mired)

    def get_questions(self) -> list[dict]:
        return [
            {
                "type": "input",
                "name": "light_entity_id",
                "message": "Specify the entity_id of your light in HA? Ex: light.hall_lamp",
                "validate": lambda val: val.startswith("light.")
                or "entity id must start with light.",
            },
            {
                "type": "input",
                "name": "light_model_id",
                "message": "What model is your light? Ex: LED1837R5",
                "validate": lambda val: len(val) > 0 or "This is required",
            },
        ]

    def process_answers(self, answers):
        self._entity_id = answers["light_entity_id"]
        self._model_id = answers["light_model_id"]

    def get_entity_state(self, entity_id: str) -> dict:
        url = self._api_url + "/states/" + entity_id
        r = requests.get(url, headers=self._auth_header)
        return r.json()

    def build_hs_json_body(self, bri: int, hue: int, sat: int) -> dict:
        return {
            "entity_id": self._entity_id,
            "brightness": bri,
            "hs_color": [hue / 65535 * 360, sat / 255 * 100],
        }

    def build_ct_json_body(self, bri: int, ct: int):
        return {"entity_id": self._entity_id, "brightness": bri, "color_temp": ct}

    def build_bri_json_body(self, bri: int):
        return {"entity_id": self._entity_id, "brightness": bri}
