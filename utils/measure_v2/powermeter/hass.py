from .powermeter import PowerMeter
import requests

class HassPowerMeter(PowerMeter):
    def __init__(
        self,
        api_url: str,
        token: str
    ):
        self._api_url = api_url
        self._auth_header = {"Authorization": "Bearer " + token}

    def get_power(self) -> float:
        url = self._api_url + "/states/" + self._entity_id
        r = requests.get(url, headers=self._auth_header)
        json = r.json()
        return float(json.get("state"))
    
    def get_questions(self) -> list[dict]:
        return [
            {
                'type': 'input',
                'name': 'powermeter_entity_id',
                'message': 'Specify the entity_id of your powermeter in HA?',
            }
        ]
    
    def process_answers(self, answers):
        self._entity_id = answers["powermeter_entity_id"]
