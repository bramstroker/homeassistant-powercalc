import requests
from .controller import LightController, LightInfo

TURN_ON_ENDPOINT = "/services/light/turn_on"

class HassLightController(LightController):
    def __init__(
        self,
        api_url: str,
        token: str
    ):
        self._api_url = api_url
        self._auth_header = {"Authorization": "Bearer " + token}

    def change_light_state(self, color_mode: str, **kwargs):
        pass

    def get_light_info(self) -> LightInfo:
        state = self.get_entity_state(self._entity_id)
        min_mired = state.get("attributes").get("min_mireds")
        max_mired = state.get("attributes").get("max_mireds")
        return LightInfo(self._model_id, min_mired, max_mired)

    def get_questions(self) -> list[dict]:
        #todo, selection list
        return [
            {
                'type': 'input',
                'name': 'light_entity_id',
                'message': 'Specify the entity_id of your light in HA?',
            },
            {
                'type': 'input',
                'name': 'light_model_id',
                'message': 'What is the model_id of your light? for example LWA004',
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
            'entity_id': self._entity_id,
            'brightness': bri,
            'hs_color': [hue/65535*360, sat/255*100]
        }


    def build_ct_json_body(self, bri: int, ct: int):
        return {
            'entity_id': self._entity_id,
            'brightness': bri,
            'color_temp': ct
        }
        

    def build_bri_json_body(self, bri: int):
        return {
            'entity_id': self._entity_id,
            'brightness': bri
        }


    def set_light_state(self, color_mode: str, **kwargs):
        if color_mode == MODE_HS:
            json = self.build_hs_json_body()
        elif color_mode == MODE_COLOR_TEMP:
            json = self.build_ct_json_body()
        else:
            json = self.build_bri_json_body()
        
        url = self._api_url + TURN_ON_ENDPOINT
        requests.post(url, json=json, headers=self._auth_header)
        #todo error handling