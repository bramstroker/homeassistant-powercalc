from __future__ import annotations

from dateutil.parser import parse
from homeassistant_api import Client

from .errors import PowerMeterError
from .powermeter import PowerMeasurementResult, PowerMeter

class HassPowerMeter(PowerMeter):
    def __init__(self, api_url: str, token: str):
        try:
            self.client = Client(api_url, token)
        except Exception as e:
            raise PowerMeterError(f"Failed to connect to HA API: {e}")

    def get_power(self) -> PowerMeasurementResult:
        state = self.client.get_state(self._entity_id)
        last_updated = parse(state.get("last_updated")).timestamp()
        return PowerMeasurementResult(float(state.get("state")), last_updated)

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
