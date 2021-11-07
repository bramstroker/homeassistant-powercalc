from __future__ import annotations

import time

from .powermeter import PowerMeasurementResult, PowerMeter

UNIT_WATT = "W"
UNIT_AMPERE = "A"
UNIT_MILI_AMPERE = "mA"
UNIT_VOLTAGE = "V"

class ManualPowerMeter(PowerMeter):
    def __init__(self):
        self._unit_of_measurement: str = UNIT_WATT
        self._voltage: int = None

    def get_power(self) -> PowerMeasurementResult:
        print('Input power measurement:')
        power = float(input())
        if self._unit_of_measurement == UNIT_AMPERE:
            power = power * self._voltage
        if self._unit_of_measurement == UNIT_MILI_AMPERE:
            power = power / 1000 * self._voltage

        return PowerMeasurementResult(power, time.time())
    
    def get_questions(self) -> list[dict]:
        return [
            {
                "type": "list",
                "name": "unit_of_measurement",
                "message": "What is your unit of measurements?",
                "default": UNIT_WATT,
                "choices": [
                    UNIT_WATT,
                    UNIT_AMPERE,
                    UNIT_MILI_AMPERE
                ]
            },
            {
                "type": "input",
                "name": "voltage",
                "message": "Input the voltage",
                "when": lambda answers: answers["unit_of_measurement"] != UNIT_WATT,
            },
        ]

    def process_answers(self, answers):
        self._unit_of_measurement = answers["unit_of_measurement"]
        if "voltage" in answers:
            self._voltage = int(answers["voltage"])
