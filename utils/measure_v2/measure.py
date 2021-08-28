from asyncio.tasks import sleep
from light_controller.const import (
    MODE_BRIGHTNESS,
    MODE_COLOR_TEMP,
    MODE_HS
)
from light_controller.controller import LightController
from light_controller.hue import HueLightController
from light_controller.hass import HassLightController
from powermeter.powermeter import PowerMeter
from powermeter.shelly import ShellyPowerMeter
import time
import json
from typing import Iterator
from PyInquirer import prompt
import os
import csv


CSV_HEADERS = {
    MODE_HS: ["bri", "hue", "sat", "watt"],
    MODE_COLOR_TEMP: ["bri", "mired", "watt"],
    MODE_BRIGHTNESS: ["bri", "watt"]
}

# Change the params below
SLEEP_TIME = 2  # time between changing the light params and taking the measurement
SLEEP_TIME_HUE = 5  # time to wait between each increase in hue
SLEEP_TIME_SAT = 10  # time to wait between each increase in saturation

# Change this when the script crashes due to connectivity issues, so you don't have to start all over again
START_BRIGHTNESS = 1
MAX_BRIGHTNESS = 255

# Power meter settings
SHELLY_IP = "192.168.178.254"

# Light controller settings
HUE_BRIDGE_IP = "192.168.178.44"

HASS_URL = "http://192.168.178.99:8123/api"
HASS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiIzNDQ3NTFjNDQ4MWQ0MzRkOWZlNmRkNWE3MzkyYzhjNCIsImlhdCI6MTYzMDE1MzUzNCwiZXhwIjoxOTQ1NTEzNTM0fQ.-hieXd-D3txoUaVeqbRBJxPZazVx6Xb7xw-QQvgBkzc"

class Measure():
    def __init__(self, light_controller: LightController, power_meter: PowerMeter):
        self.light_controller = light_controller
        self.power_meter = power_meter

    def start(self):
        answers = prompt(self.get_questions())
        self.light_controller.process_answers(answers)
        self.light_info = self.light_controller.get_light_info()

        color_mode = answers["color_mode"]

        export_directory = os.path.join(
            os.path.dirname(__file__),
            "export",
            self.light_info.model_id
        )
        if not os.path.exists(export_directory):
            os.makedirs(export_directory)

        if answers["generate_model_json"]:
            standby_usage = self.measure_standby_usage()
            self.write_model_json(directory=export_directory, standby_usage=standby_usage, name=answers["model_name"])

        with open(f"{export_directory}/{color_mode}.csv", "w") as csv_file:
            csv_writer = csv.writer(csv_file)

            self.light_controller.change_light_state(MODE_BRIGHTNESS, on=True, bri=1)

            # Initially wait longer so the smartplug can settle
            print("Start taking measurements for color mode: ", color_mode)
            print("Waiting 10 seconds...")
            time.sleep(10)

            csv_writer.writerow(CSV_HEADERS[color_mode])
            for count, variation in enumerate(self.get_variations(color_mode)):
                print("Changing light to: ", variation)
                self.light_controller.change_light_state(color_mode, on=True, **variation)
                time.sleep(SLEEP_TIME)
                power = self.power_meter.get_power()
                print("Measured power: ", power)
                print()
                row = list(variation.values())
                row.append(power)
                csv_writer.writerow(row)
                if count % 100 == 0:
                    csv_file.flush()

            csv_file.close()

    def measure_standby_usage(self) -> float:
        self.light_controller.change_light_state(on=False)
        print("Measuring standby usage. Waiting for 5 seconds...")
        time.sleep(5)
        return self.power_meter.get_power()
    
    def get_variations(self, color_mode: str):
        if color_mode == MODE_HS:
            yield from self.get_hs_variations()
        elif color_mode == MODE_COLOR_TEMP:
            yield from self.get_ct_variations()
        else:
            yield from self.get_brightness_variations()

    def get_ct_variations(self) -> Iterator[dict]:
        min_mired = self.light_info.min_mired
        max_mired = self.light_info.max_mired
        for bri in self.inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 5):
            for mired in self.inclusive_range(min_mired, max_mired, 10):
                yield {"bri": bri, "ct": mired}


    def get_hs_variations(self) -> Iterator[dict]:
        for bri in self.inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 10):
            for sat in self.inclusive_range(1, 254, 10):
                time.sleep(SLEEP_TIME_SAT)
                for hue in self.inclusive_range(1, 65535, 2000):
                    time.sleep(SLEEP_TIME_HUE)
                    yield {"bri": bri, "hue": hue, "sat": sat}


    def get_brightness_variations(self) -> Iterator[dict]:
        for bri in self.inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 1):
            yield {"bri": bri}


    def inclusive_range(self, start: int, end: int, step: int) -> Iterator[int]:
        i = start
        while i < end:
            yield i
            i += step
        yield end

    def write_model_json(directory: str, standby_usage: float, name: str):
        json_data = json.dumps({
            "name": name,
            "standby_usage": standby_usage,
            "supported_modes": [
                "lut"
            ]
        })
        json_file = open(os.path.join(directory, "model.json"), "w")
        json_file.write(json_data)
        json_file.close()
    
    def get_questions(self) -> list[dict]:
        return [
            {
                'type': 'list',
                'name': 'color_mode',
                'message': 'Select the color mode?',
                'default': MODE_HS,
                'choices': [MODE_HS, MODE_COLOR_TEMP, MODE_BRIGHTNESS],
            },
            {
                'type': 'confirm',
                'message': 'Do you want to generate model.json?',
                'name': 'generate_model_json',
                'default': True,
            },
            {
                'type': 'input',
                'name': 'model_name',
                'message': 'Specify the full light model name',
                'when': lambda answers: answers['generate_model_json']
            },
        ] + self.light_controller.get_questions()


def create_light_controller() -> LightController:
    #return HueLightController(HUE_BRIDGE_IP)
    return HassLightController(HASS_URL, HASS_TOKEN)

def create_power_meter() -> PowerMeter:
    return ShellyPowerMeter(SHELLY_IP)

measure = Measure(
    create_light_controller(),
    create_power_meter()
)

measure.start()
