from __future__ import annotations

import requests
from dateutil.parser import parse

from .powermeter import PowerMeasurementResult, PowerMeter


class HassPowerMeter(PowerMeter):
    def __init__(self, api_url: str, token: str):
        self._api_url = api_url
        self._auth_header = {"Authorization": "Bearer " + token}

    def get_power(self) -> PowerMeasurementResult:
        url = self._api_url + "/states/" + self._entity_id
        r = requests.get(url, headers=self._auth_header)
        json = r.json()
        last_updated = parse(json.get("last_updated")).timestamp()
        return PowerMeasurementResult(float(json.get("state")), last_updated)

    def get_questions(self) -> list[dict]:
        return [
            {
                "type": "input",
                "name": "powermeter_entity_id",
                "message": "Specify the entity_id of your powermeter in HA? Ex: sensor.fibaro_fgwp102_power",
            }
        ]

    def process_answers(self, answers):
        self._entity_id = answers["powermeter_entity_id"]
