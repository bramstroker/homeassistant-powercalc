from dateutil.parser import parse
from .errors import PowerMeterError
from .powermeter import PowerMeter
import requests
import time;

MAX_RETRIES = 10

class HassPowerMeter(PowerMeter):
    def __init__(
        self,
        api_url: str,
        token: str
    ):
        self._api_url = api_url
        self._auth_header = {"Authorization": "Bearer " + token}

    def get_power(self) -> float:
        current_timestamp = time.time()
        i = 0
        while i < MAX_RETRIES:
            url = self._api_url + "/states/" + self._entity_id
            r = requests.get(url, headers=self._auth_header)
            json = r.json()
            last_updated = parse(json.get("last_updated")).timestamp()
            if last_updated > current_timestamp:
                # We have a recent reading. Return the power.
                return float(json.get("state"))

            time.sleep(1)
            i += 1
        
        raise PowerMeterError("Could not get a recent power measurement. Aborting..")

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
