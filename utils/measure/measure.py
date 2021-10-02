from __future__ import annotations

import csv
import gzip
import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass
from typing import Iterator, Optional

from decouple import config
from light_controller.const import MODE_BRIGHTNESS, MODE_COLOR_TEMP, MODE_HS
from light_controller.controller import LightController
from light_controller.errors import LightControllerError
from light_controller.hass import HassLightController
from light_controller.hue import HueLightController
from powermeter.errors import OutdatedMeasurementError, PowerMeterError
from powermeter.hass import HassPowerMeter
from powermeter.kasa import KasaPowerMeter
from powermeter.powermeter import PowerMeter
from powermeter.shelly import ShellyPowerMeter
from powermeter.tasmota import TasmotaPowerMeter
from powermeter.tuya import TuyaPowerMeter
from PyInquirer import prompt

CSV_HEADERS = {
    MODE_HS: ["bri", "hue", "sat", "watt"],
    MODE_COLOR_TEMP: ["bri", "mired", "watt"],
    MODE_BRIGHTNESS: ["bri", "watt"],
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
    POWER_METER_TUYA,
]

SELECTED_POWER_METER = config("POWER_METER")

LIGHT_CONTROLLER_HUE = "hue"
LIGHT_CONTROLLER_HASS = "hass"
LIGHT_CONTROLLERS = [LIGHT_CONTROLLER_HUE, LIGHT_CONTROLLER_HASS]

SELECTED_LIGHT_CONTROLLER = config("LIGHT_CONTROLLER")

LOG_LEVEL = config("LOG_LEVEL", default=logging.INFO)
SLEEP_INITIAL = 10
SLEEP_STANDBY = 5
SLEEP_TIME = config("SLEEP_TIME", default=2, cast=int)
SLEEP_TIME_HUE = config("SLEEP_TIME_HUE", default=5, cast=int)
SLEEP_TIME_SAT = config("SLEEP_TIME_SAT", default=10, cast=int)
SLEEP_TIME_CT = config("SLEEP_TIME_CT", default=10, cast=int)
START_BRIGHTNESS = config("START_BRIGHTNESS", default=1, cast=int)
MAX_RETRIES = config("MAX_RETRIES", default=5, cast=int)
SAMPLE_COUNT = config("SAMPLE_COUNT", default=1, cast=int)

SHELLY_IP = config("SHELLY_IP")
TUYA_DEVICE_ID = config("TUYA_DEVICE_ID")
TUYA_DEVICE_IP = config("TUYA_DEVICE_IP")
TUYA_DEVICE_KEY = config("TUYA_DEVICE_KEY")
TUYA_DEVICE_VERSION = config("EMAIL_PORT", default="3.3")
HUE_BRIDGE_IP = config("HUE_BRIDGE_IP")
HASS_URL = config("HASS_URL")
HASS_TOKEN = config("HASS_TOKEN")
TASMOTA_DEVICE_IP = config("TASMOTA_DEVICE_IP")
KASA_DEVICE_IP = config("KASA_DEVICE_IP")

CSV_WRITE_BUFFER = 50

logging.basicConfig(
    level=logging.getLevelName(LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("measure.log"),
        logging.StreamHandler()
    ]
)

_LOGGER = logging.getLogger("measure")

class Measure:
    def __init__(self, light_controller: LightController, power_meter: PowerMeter):
        self.light_controller = light_controller
        self.power_meter = power_meter

    def start(self):
        answers = prompt(self.get_questions())
        self.light_controller.process_answers(answers)
        self.power_meter.process_answers(answers)
        self.color_mode = answers["color_mode"]
        self.num_lights = int(answers.get("num_lights", 1))

        self.light_info = self.light_controller.get_light_info()

        export_directory = os.path.join(
            os.path.dirname(__file__), "export", self.light_info.model_id
        )
        if not os.path.exists(export_directory):
            os.makedirs(export_directory)

        if answers["generate_model_json"]:
            standby_power = self.measure_standby_power()
            self.write_model_json(
                directory=export_directory,
                standby_power=standby_power,
                name=answers["model_name"],
                measure_device=answers["measure_device"],
            )

        csv_file_path = f"{export_directory}/{self.color_mode}.csv"

        resume_at = None
        file_write_mode = "w"
        write_header_row = True
        if self.should_resume(csv_file_path):
            resume_at = self.get_resume_variation(csv_file_path)
            file_write_mode = "a"
            write_header_row = False

        with open(csv_file_path, file_write_mode, newline="") as csv_file:
            csv_writer = csv.writer(csv_file)

            self.light_controller.change_light_state(MODE_BRIGHTNESS, on=True, bri=1)

            # Initially wait longer so the smartplug can settle
            _LOGGER.info(f"Start taking measurements for color mode: {self.color_mode}")
            _LOGGER.info(f"Waiting {SLEEP_INITIAL} seconds...")
            time.sleep(SLEEP_INITIAL)

            if write_header_row:
                csv_writer.writerow(CSV_HEADERS[self.color_mode])
            previous_variation = None
            for count, variation in enumerate(self.get_variations(self.color_mode, resume_at)):
                _LOGGER.info(f"Changing light to: {variation}")
                variation_start_time = time.time()
                self.light_controller.change_light_state(
                    self.color_mode, on=True, **asdict(variation)
                )

                if previous_variation and isinstance(variation, ColorTempVariation) and variation.ct < previous_variation.ct:
                    _LOGGER.info("Extra waiting for significant CT change...")
                    time.sleep(SLEEP_TIME_CT)

                if previous_variation and isinstance(variation, HsVariation) and variation.sat < previous_variation.sat:
                    _LOGGER.info("Extra waiting for significant SAT change...")
                    time.sleep(SLEEP_TIME_SAT)

                if previous_variation and isinstance(variation, HsVariation) and variation.hue < previous_variation.hue:
                    _LOGGER.info("Extra waiting for significant HUE change...")
                    time.sleep(SLEEP_TIME_HUE)

                previous_variation = variation
                time.sleep(SLEEP_TIME)
                power = self.take_power_measurement(variation_start_time)
                _LOGGER.info(f"Measured power: {power}")
                row = variation.to_csv_row()
                row.append(power)
                csv_writer.writerow(row)
                if count % CSV_WRITE_BUFFER == 1:
                    csv_file.flush()
                    _LOGGER.debug("Flushing CSV buffer")

            csv_file.close()

        if answers["gzip"] or True:
            self.gzip_csv(csv_file_path)


    def should_resume(self, csv_file_path) -> bool:
        if not os.path.exists(csv_file_path):
            return False
        
        answers = prompt([{
            "type": "confirm",
            "message": "CSV File already exists. Do you want to resume measurements?",
            "name": "resume",
            "default": True,
        },])

        return answers["resume"]


    def get_resume_variation(self, csv_file_path: str) -> Variation:
        with open(csv_file_path, "r") as csv_file:
            rows = csv.reader(csv_file)
            last_row = list(rows)[-1]

        if self.color_mode == MODE_BRIGHTNESS:
            return Variation(bri=int(last_row[0]))

        if self.color_mode == MODE_COLOR_TEMP:
            return ColorTempVariation(bri=int(last_row[0]), ct=int(last_row[1]))

        if self.color_mode == MODE_HS:
            return HsVariation(bri=int(last_row[0]), hue=int(last_row[1]), sat=int(last_row[2]))

        raise Exception(f"Color mode {self.color_mode} not supported")


    def take_power_measurement(self, start_timestamp: float, retry_count=0) -> float:
        measurements = []
        # Take multiple samples to reduce noise
        for i in range(SAMPLE_COUNT):
            _LOGGER.debug(f"Taking sample {i}")
            try:
                measurement = self.power_meter.get_power()
            except PowerMeterError as err:
                if retry_count == MAX_RETRIES:
                    raise err

                retry_count += 1
                self.take_power_measurement(start_timestamp, retry_count)

            # Check if measurement is not outdated
            if measurement.updated < start_timestamp:
                # Prevent endless recursion and raise exception
                if retry_count == MAX_RETRIES:
                    raise OutdatedMeasurementError(
                        "Power measurement is outdated. Aborting after {} retries".format(
                            MAX_RETRIES
                        )
                    )

                retry_count += 1
                time.sleep(1)
                self.take_power_measurement(start_timestamp, retry_count)

            measurements.append(measurement.power)
            time.sleep(0.5)

        avg = sum(measurements) / len(measurements) / self.num_lights
        return round(avg, 2)

    def gzip_csv(self, csv_file_path: str):
        with open(csv_file_path, "rb") as csv_file:
            with gzip.open(f"{csv_file_path}.gz", "wb") as gzip_file:
                shutil.copyfileobj(csv_file, gzip_file)


    def measure_standby_power(self) -> float:
        self.light_controller.change_light_state(MODE_BRIGHTNESS, on=False)
        start_time = time.time()
        _LOGGER.info(f"Measuring standby power. Waiting for {SLEEP_STANDBY} seconds...")
        time.sleep(SLEEP_STANDBY)
        return self.take_power_measurement(start_time)

    def get_variations(self, color_mode: str, resume_at: Optional[Variation] = None) -> Iterator[Variation]:
        if color_mode == MODE_HS:
            variations = self.get_hs_variations()
        elif color_mode == MODE_COLOR_TEMP:
            variations = self.get_ct_variations()
        else:
            variations = self.get_brightness_variations()
        
        if resume_at:
            include_variation = False
            for variation in variations:
                if include_variation:
                    yield variation

                # Current variation is the one we need to resume at.
                # Set include_variation flag so it every variation from now on will be yielded next iteration
                if variation == resume_at:
                    include_variation = True
        else:
            yield from variations

    def get_ct_variations(self) -> Iterator[ColorTempVariation]:
        min_mired = self.light_info.min_mired
        max_mired = self.light_info.max_mired
        for bri in self.inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 5):
            for mired in self.inclusive_range(min_mired, max_mired, 10):
                yield ColorTempVariation(bri=bri, ct=mired)

    def get_hs_variations(self) -> Iterator[HsVariation]:
        for bri in self.inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 10):
            for sat in self.inclusive_range(1, MAX_SAT, 10):
                for hue in self.inclusive_range(1, MAX_HUE, 2000):
                    yield HsVariation(bri=bri, hue=hue, sat=sat)

    def get_brightness_variations(self) -> Iterator[Variation]:
        for bri in self.inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 1):
            yield Variation(bri=bri)

    def inclusive_range(self, start: int, end: int, step: int) -> Iterator[int]:
        i = start
        while i < end:
            yield i
            i += step
        yield end

    def write_model_json(
        self, directory: str, standby_power: float, name: str, measure_device: str
    ):
        json_data = json.dumps(
            {
                "measure_device": measure_device,
                "measure_method": "script",
                "measure_description": "Measured with utils/measure script",
                "measure_settings": {
                    "SAMPLE_COUNT": SAMPLE_COUNT,
                    "SLEEP_TIME": SLEEP_TIME
                },
                "name": name,
                "standby_power": standby_power,
                "supported_modes": ["lut"],
            },
            indent=4,
            sort_keys=True,
        )
        json_file = open(os.path.join(directory, "model.json"), "w")
        json_file.write(json_data)
        json_file.close()

    def get_questions(self) -> list[dict]:
        return (
            [
                {
                    "type": "list",
                    "name": "color_mode",
                    "message": "Select the color mode?",
                    "default": MODE_HS,
                    "choices": [MODE_HS, MODE_COLOR_TEMP, MODE_BRIGHTNESS],
                },
                {
                    "type": "confirm",
                    "message": "Do you want to generate model.json?",
                    "name": "generate_model_json",
                    "default": True,
                },
                {
                    "type": "input",
                    "name": "model_name",
                    "message": "Specify the full light model name",
                    "when": lambda answers: answers["generate_model_json"],
                },
                {
                    "type": "input",
                    "name": "measure_device",
                    "message": "Which device (manufacturer, model) do you use to take the measurement?",
                    "when": lambda answers: answers["generate_model_json"],
                },
                {
                    "type": "confirm",
                    "message": "Do you want to gzip CSV files?",
                    "name": "gzip",
                    "default": True,
                },
                {
                    "type": "confirm",
                    "name": "multiple_lights",
                    "message": "Are you measuring multiple lights. In some situations it helps to connect multiple lights to be able to measure low currents.",
                    "default": False
                },
                {
                    "type": "input",
                    "name": "num_lights",
                    "message": "Hpw many lights are you measuring?",
                    "when": lambda answers: answers["multiple_lights"],
                },
            ]
            + self.light_controller.get_questions()
            + self.power_meter.get_questions()
        )

@dataclass(frozen=True)
class Variation:
    bri: int

    def to_csv_row(self) -> list:
        return [self.bri]

@dataclass(frozen=True)
class HsVariation(Variation):
    hue: int
    sat: int

    def to_csv_row(self) -> list:
        return [self.bri, self.hue, self.sat]
    
    def is_hue_changed(self, other_variation: HsVariation):
        return self.hue != other_variation.hue
    
    def is_sat_changed(self, other_variation: HsVariation):
        return self.sat != other_variation.sat

@dataclass(frozen=True)
class ColorTempVariation(Variation):
    ct: int

    def to_csv_row(self) -> list:
        return [self.bri, self.ct]
    
    def is_ct_changed(self, other_variation: ColorTempVariation):
        return self.ct != other_variation.ct

class LightControllerFactory:
    def hass(self):
        return HassLightController(HASS_URL, HASS_TOKEN)

    def hue(self):
        return HueLightController(HUE_BRIDGE_IP)

    def create(self) -> LightController:
        factories = {LIGHT_CONTROLLER_HUE: self.hue, LIGHT_CONTROLLER_HASS: self.hass}
        factory = factories.get(SELECTED_LIGHT_CONTROLLER)
        if factory is None:
            raise Exception(f"Could not find a factory for {SELECTED_LIGHT_CONTROLLER}")

        _LOGGER.info(f"Selected Light controller: {SELECTED_LIGHT_CONTROLLER}")
        return factory()


class PowerMeterFactory:
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
            TUYA_DEVICE_ID, TUYA_DEVICE_IP, TUYA_DEVICE_KEY, TUYA_DEVICE_VERSION
        )

    def create(self) -> PowerMeter:
        factories = {
            POWER_METER_HASS: self.hass,
            POWER_METER_KASA: self.kasa,
            POWER_METER_SHELLY: self.shelly,
            POWER_METER_TASMOTA: self.tasmota,
            POWER_METER_TUYA: self.tuya,
        }
        factory = factories.get(SELECTED_POWER_METER)
        if factory is None:
            raise PowerMeterError(f"Could not find a factory for {SELECTED_POWER_METER}")

        _LOGGER.info(f"Selected powermeter: {SELECTED_POWER_METER}")
        return factory()

def main():
    light_controller_factory = LightControllerFactory()
    power_meter_factory = PowerMeterFactory()

    try:
        power_meter = power_meter_factory.create()
    except PowerMeterError as e:
        _LOGGER.error(f"Aborting: {e}")
        return

    try:
        light_controller = light_controller_factory.create()
    except LightControllerError as e:
        _LOGGER.error(f"Aborting: {e}")
        return

    measure = Measure(light_controller, power_meter)

    measure.start()

if __name__ == "__main__":
    main()
