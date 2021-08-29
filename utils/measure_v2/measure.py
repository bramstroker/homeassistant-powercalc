from __future__ import annotations

from light_controller.const import (
    MODE_BRIGHTNESS,
    MODE_COLOR_TEMP,
    MODE_HS
)
from light_controller.controller import LightController
from light_controller.hue import HueLightController
from light_controller.hass import HassLightController
from powermeter.powermeter import PowerMeter
from powermeter.hass import HassPowerMeter
from powermeter.kasa import KasaPowerMeter
from powermeter.shelly import ShellyPowerMeter
from powermeter.tasmota import TasmotaPowerMeter
from powermeter.tuya import TuyaPowerMeter
from decouple import config
import time
import json
from typing import Iterator
from PyInquirer import prompt
import os
import csv
import gzip
import shutil

CSV_HEADERS = {
    MODE_HS: ["bri", "hue", "sat", "watt"],
    MODE_COLOR_TEMP: ["bri", "mired", "watt"],
    MODE_BRIGHTNESS: ["bri", "watt"]
}
MAX_BRIGHTNESS = 255
MAX_SAT = 254
MAX_HUE = 65535

POWER_METER_HASS = "hass"
POWER_METER_KASA = "kasa"
POWER_METER_SHELLY = "shelly"
POWER_METER_TASMOTA = "tasmota"
POWER_METER_TUYA = "tuya"
POWER_METERS = [
    POWER_METER_HASS,
    POWER_METER_KASA,
    POWER_METER_SHELLY,
    POWER_METER_TASMOTA,
    POWER_METER_TUYA
]

SELECTED_POWER_METER = config('POWER_METER')

LIGHT_CONTROLLER_HUE = "hue"
LIGHT_CONTROLLER_HASS = "hass"
LIGHT_CONTROLLERS = [
    LIGHT_CONTROLLER_HUE,
    LIGHT_CONTROLLER_HASS
]

SELECTED_LIGHT_CONTROLLER = config('LIGHT_CONTROLLER')

# Change the params below
SLEEP_TIME = config('SLEEP_TIME', default=2, cast=int)
SLEEP_TIME_HUE = config('SLEEP_TIME_HUE', default=5, cast=int)
SLEEP_TIME_SAT = config('SLEEP_TIME_SAT', default=10, cast=int)

# Change this when the script crashes due to connectivity issues, so you don't have to start all over again
START_BRIGHTNESS = config('START_BRIGHTNESS', default=1, cast=int)

SHELLY_IP = config('SHELLY_IP')
TUYA_DEVICE_ID = config('TUYA_DEVICE_ID')
TUYA_DEVICE_IP = config('TUYA_DEVICE_IP')
TUYA_DEVICE_KEY = config('TUYA_DEVICE_KEY')
TUYA_DEVICE_VERSION = config('EMAIL_PORT', default='3.3')
HUE_BRIDGE_IP = config('HUE_BRIDGE_IP')
HASS_URL = config('HASS_URL')
HASS_TOKEN = config('HASS_TOKEN')
TASMOTA_DEVICE_IP = config('TASMOTA_DEVICE_IP')
KASA_DEVICE_IP = config('KASA_DEVICE_IP')

class Measure():
    def __init__(self, light_controller: LightController, power_meter: PowerMeter):
        self.light_controller = light_controller
        self.power_meter = power_meter

    def start(self):
        answers = prompt(self.get_questions())
        self.light_controller.process_answers(answers)
        self.power_meter.process_answers(answers)
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
            self.write_model_json(
                directory=export_directory,
                standby_usage=standby_usage,
                name=answers["model_name"],
                measure_device=answers["measure_device"]
            )

        csv_file_path = f"{export_directory}/{color_mode}.csv"
        with open(csv_file_path, "w") as csv_file:
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
        
        if answers["gzip"] or True:
            self.gzip_csv(csv_file_path)
    
    def gzip_csv(self, csv_file_path: str):
        with open(csv_file_path, "rb") as csv_file:
                with gzip.open(f"{csv_file_path}.gz", 'wb') as gzip_file:
                    shutil.copyfileobj(csv_file, gzip_file)

    def measure_standby_usage(self) -> float:
        self.light_controller.change_light_state(MODE_BRIGHTNESS, on=False)
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
            for sat in self.inclusive_range(1, MAX_SAT, 10):
                time.sleep(SLEEP_TIME_SAT)
                for hue in self.inclusive_range(1, MAX_HUE, 2000):
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

    def write_model_json(
        self,
        directory: str,
        standby_usage: float,
        name: str,
        measure_device: str
    ):
        json_data = json.dumps({
            "measure_device": measure_device,
            "measure_method": "script",
            "name": name,
            "standby_usage": standby_usage,
            "supported_modes": [
                "lut"
            ]
        }, indent=4, sort_keys=True)
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
            {
                'type': 'input',
                'name': 'measure_device',
                'message': 'Which device (manufacturer, model) do you use to take the measurement?',
                'when': lambda answers: answers['generate_model_json']
            },
            {
                'type': 'confirm',
                'message': 'Do you want to gzip CSV files?',
                'name': 'gzip',
                'default': True,
            },
        ] + self.light_controller.get_questions() + self.power_meter.get_questions()


class LightControllerFactory():
    def hass(self):
        return HassLightController(HASS_URL, HASS_TOKEN)
    
    def hue(self):
        return HueLightController(HUE_BRIDGE_IP)
    
    def create(self) -> LightController:
        factories = {
            LIGHT_CONTROLLER_HUE: self.hue,
            LIGHT_CONTROLLER_HASS: self.hass
        }
        factory = factories.get(SELECTED_LIGHT_CONTROLLER)
        if factory is None:
            print("factory not found")
            #todo exception

        print("light controller", SELECTED_LIGHT_CONTROLLER)
        return factory()


class PowerMeterFactory():
    def hass(self):
        return HassPowerMeter(HASS_URL, HASS_TOKEN)
    
    def kasa(self):
        return KasaPowerMeter(KASA_DEVICE_IP)

    def shelly(self):
        return ShellyPowerMeter(SHELLY_IP)
    
    def tasmota(self):
        return TasmotaPowerMeter(TASMOTA_DEVICE_IP)

    def tuya(self):
        return TuyaPowerMeter(
            TUYA_DEVICE_ID,
            TUYA_DEVICE_IP,
            TUYA_DEVICE_KEY,
            TUYA_DEVICE_VERSION
        )
    
    def create(self) -> PowerMeter:
        factories = {
            POWER_METER_HASS: self.hass,
            POWER_METER_KASA: self.kasa,
            POWER_METER_SHELLY: self.shelly,
            POWER_METER_TASMOTA: self.tasmota,
            POWER_METER_TUYA: self.tuya
        }
        factory = factories.get(SELECTED_POWER_METER)
        if factory is None:
            print("factory not found")
            #todo exception

        print("powermeter", SELECTED_POWER_METER)
        return factory()


light_controller_factory = LightControllerFactory()
power_meter_factory = PowerMeterFactory()
measure = Measure(
    light_controller_factory.create(),
    power_meter_factory.create()
)

measure.start()
