from __future__ import annotations

import csv
import gzip
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime as dt
from io import TextIOWrapper
from typing import Iterator, Optional

from decouple import Choices, config
from light_controller.const import MODE_BRIGHTNESS, MODE_COLOR_TEMP, MODE_HS
from light_controller.controller import LightController
from light_controller.errors import LightControllerError
from light_controller.hass import HassLightController
from light_controller.hue import HueLightController
from powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from powermeter.errors import OutdatedMeasurementError, PowerMeterError, ZeroReadingError
from powermeter.dummy import DummyPowerMeter
from powermeter.hass import HassPowerMeter
from powermeter.kasa import KasaPowerMeter
from powermeter.manual import ManualPowerMeter
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

MIN_BRIGHTNESS = min(max(
    config(
        "MIN_BRIGHTNESS",
        default=config("START_BRIGHTNESS", default=1, cast=int),
        cast=int
    ), 1), 255
)
MAX_BRIGHTNESS = 255
MIN_SAT = min(max(config("MIN_SAT", default=1, cast=int), 1), 254)
MAX_SAT = min(max(config("MAX_SAT", default=254, cast=int), 1), 254)
MIN_HUE = min(max(config("MIN_HUE", default=1, cast=int), 1), 65535)
MAX_HUE = min(max(config("MAX_HUE", default=65535, cast=int), 1), 65535)
CT_BRI_STEPS = min(config("CT_BRI_STEPS", default=5, cast=int), 10)
CT_MIRED_STEPS = min(config("CT_BRI_STEPS", default=10, cast=int), 10)
BRI_BRI_STEPS = 1
HS_BRI_STEPS = min(config("HS_BRI_STEPS", default=10, cast=int), 20)
HS_HUE_STEPS = min(config("HS_HUE_STEPS", default=2000, cast=int), 4000)
HS_SAT_STEPS = min(config("HS_SAT_STEPS", default=10, cast=int), 20)

POWER_METER_DUMMY = "dummy"
POWER_METER_HASS = "hass"
POWER_METER_KASA = "kasa"
POWER_METER_MANUAL = "manual"
POWER_METER_SHELLY = "shelly"
POWER_METER_TASMOTA = "tasmota"
POWER_METER_TUYA = "tuya"
POWER_METERS = [
    POWER_METER_DUMMY,
    POWER_METER_HASS,
    POWER_METER_KASA,
    POWER_METER_MANUAL,
    POWER_METER_SHELLY,
    POWER_METER_TASMOTA,
    POWER_METER_TUYA,
]

SELECTED_POWER_METER = config("POWER_METER", cast=Choices(POWER_METERS))

LIGHT_CONTROLLER_DUMMY = "dummy"
LIGHT_CONTROLLER_HUE = "hue"
LIGHT_CONTROLLER_HASS = "hass"
LIGHT_CONTROLLERS = [
    LIGHT_CONTROLLER_DUMMY,
    LIGHT_CONTROLLER_HUE,
    LIGHT_CONTROLLER_HASS
]

SELECTED_LIGHT_CONTROLLER = config("LIGHT_CONTROLLER", cast=Choices(LIGHT_CONTROLLERS))

LOG_LEVEL = config("LOG_LEVEL", default=logging.INFO)
SLEEP_INITIAL = 10
SLEEP_STANDBY = config("SLEEP_STANDBY", default=20, cast=int)
SLEEP_TIME = config("SLEEP_TIME", default=2, cast=int)
SLEEP_TIME_SAMPLE = config("SLEEP_TIME_SAMPLE", default=1, cast=int)
SLEEP_TIME_HUE = config("SLEEP_TIME_HUE", default=5, cast=int)
SLEEP_TIME_SAT = config("SLEEP_TIME_SAT", default=10, cast=int)
SLEEP_TIME_CT = config("SLEEP_TIME_CT", default=10, cast=int)
MAX_RETRIES = config("MAX_RETRIES", default=5, cast=int)
SAMPLE_COUNT = config("SAMPLE_COUNT", default=1, cast=int)

SHELLY_IP = config("SHELLY_IP")
SHELLY_TIMEOUT = config("SHELLY_TIMEOUT", default=5, cast=int)
TUYA_DEVICE_ID = config("TUYA_DEVICE_ID")
TUYA_DEVICE_IP = config("TUYA_DEVICE_IP")
TUYA_DEVICE_KEY = config("TUYA_DEVICE_KEY")
TUYA_DEVICE_VERSION = config("TUYA_DEVICE_VERSION", default="3.3")
HUE_BRIDGE_IP = config("HUE_BRIDGE_IP")
HASS_URL = config("HASS_URL")
HASS_TOKEN = config("HASS_TOKEN")
TASMOTA_DEVICE_IP = config("TASMOTA_DEVICE_IP")
KASA_DEVICE_IP = config("KASA_DEVICE_IP")

CSV_ADD_DATETIME_COLUMN = config("CSV_ADD_DATETIME_COLUMN", default=False, cast=bool)

# Change some settings when selected power meter is manual
if SELECTED_POWER_METER == POWER_METER_MANUAL:
    SAMPLE_COUNT = 1
    BRI_BRI_STEPS = 3
    CT_BRI_STEPS = 15
    CT_MIRED_STEPS = 50

CSV_WRITE_BUFFER = 50
MAX_ALLOWED_0_READINGS = 50

logging.basicConfig(
    level=logging.getLevelName(LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(sys.path[0], "measure.log")),
        logging.StreamHandler()
    ]
)

_LOGGER = logging.getLogger("measure")

with open(os.path.join(sys.path[0], ".VERSION"), "r") as f:
    _VERSION = f.read().strip()

class Measure:
    def __init__(self, light_controller: LightController, power_meter: PowerMeter):
        self.light_controller = light_controller
        self.power_meter = power_meter
        self.num_0_readings: int = 0

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

        csv_file_path = f"{export_directory}/{self.color_mode}.csv"

        resume_at = None
        file_write_mode = "w"
        write_header_row = True
        if self.should_resume(csv_file_path):
            resume_at = self.get_resume_variation(csv_file_path)
            file_write_mode = "a"
            write_header_row = False

        variations = list(self.get_variations(self.color_mode, resume_at))
        num_variations = len(variations)

        _LOGGER.info(f"Starting measurements. Estimated duration: {self.calculate_time_left(variations, variations[0])}")

        if answers["generate_model_json"]:
            try:
                standby_power = self.measure_standby_power()
            except PowerMeterError as error:
                _LOGGER.error(f"Aborting: {error}")
                return
            
            self.write_model_json(
                directory=export_directory,
                standby_power=standby_power,
                name=answers["model_name"],
                measure_device=answers["measure_device"],
            )

        with open(csv_file_path, file_write_mode, newline="") as csv_file:
            csv_writer = CsvWriter(csv_file, self.color_mode, write_header_row)

            self.light_controller.change_light_state(MODE_BRIGHTNESS, on=True, bri=1)

            # Initially wait longer so the smartplug can settle
            _LOGGER.info(f"Start taking measurements for color mode: {self.color_mode}")
            _LOGGER.info(f"Waiting {SLEEP_INITIAL} seconds...")
            time.sleep(SLEEP_INITIAL)

            previous_variation = None
            for count, variation in enumerate(variations):
                if count % 10 == 0:
                    time_left = self.calculate_time_left(variations, variation, count)
                    progress_percentage = round(count / num_variations * 100)
                    _LOGGER.info(f"Progress: {progress_percentage}%, Estimated time left: {time_left}")
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
                try:
                    power = self.take_power_measurement(variation_start_time)
                except ZeroReadingError as error:
                    self.num_0_readings += 1
                    _LOGGER.warning(f"Discarding measurement: {error}")
                    if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                        _LOGGER.error("Aborting measurement session. Received to much 0 readings")
                        return
                    continue
                except PowerMeterError as error:
                    _LOGGER.error(f"Aborting: {error}")
                    return
                _LOGGER.info(f"Measured power: {power}")
                csv_writer.write_measurement(variation, power)

            csv_file.close()

        if answers["gzip"] or True:
            self.gzip_csv(csv_file_path)

    def should_resume(self, csv_file_path: str) -> bool:
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


    def take_power_measurement(self, start_timestamp: float, retry_count: int=0) -> float:
        measurements = []
        # Take multiple samples to reduce noise
        for i in range(1, SAMPLE_COUNT + 1):
            _LOGGER.debug(f"Taking sample {i}")
            try:
                measurement = self.power_meter.get_power()
                updated_at = dt.fromtimestamp(measurement.updated).strftime("%d-%m-%Y, %H:%M:%S")
                _LOGGER.debug(f"Measurement received (update_time={updated_at})")
            except PowerMeterError as err:
                if retry_count == MAX_RETRIES:
                    raise err

                retry_count += 1
                self.take_power_measurement(start_timestamp, retry_count)

            # Check if measurement is not outdated
            if measurement.updated < start_timestamp:
                # Prevent endless recursion and raise exception
                if retry_count == MAX_RETRIES:
                    raise OutdatedMeasurementError(f"Power measurement is outdated. Aborting after {MAX_RETRIES} retries")

                retry_count += 1
                time.sleep(SLEEP_TIME)
                self.take_power_measurement(start_timestamp, retry_count)
            
            # Check if we not have a 0 reading
            if measurement.power == 0:
                raise ZeroReadingError("0 watt was read from the power meter")

            measurements.append(measurement.power)
            if SAMPLE_COUNT > 1:
                time.sleep(SLEEP_TIME_SAMPLE)

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
        for bri in self.inclusive_range(MIN_BRIGHTNESS, MAX_BRIGHTNESS, CT_BRI_STEPS):
            for mired in self.inclusive_range(min_mired, max_mired, CT_MIRED_STEPS):
                yield ColorTempVariation(bri=bri, ct=mired)

    def get_hs_variations(self) -> Iterator[HsVariation]:
        for bri in self.inclusive_range(MIN_BRIGHTNESS, MAX_BRIGHTNESS, HS_BRI_STEPS):
            for sat in self.inclusive_range(MIN_SAT, MAX_SAT, HS_SAT_STEPS):
                for hue in self.inclusive_range(MIN_HUE, MAX_HUE, HS_HUE_STEPS):
                    yield HsVariation(bri=bri, hue=hue, sat=sat)

    def get_brightness_variations(self) -> Iterator[Variation]:
        for bri in self.inclusive_range(MIN_BRIGHTNESS, MAX_BRIGHTNESS, BRI_BRI_STEPS):
            yield Variation(bri=bri)

    def inclusive_range(self, start: int, end: int, step: int) -> Iterator[int]:
        i = start
        while i < end:
            yield i
            i += step
        yield end

    def calculate_time_left(self, variations: list[Variation], current_variation: Variation = None, progress: int = 0) -> str:
        """Try to guess the remaining time left. This will not account for measuring errors / retries obviously"""
        num_variations_left = len(variations) - progress

        # Account estimated seconds for the light_controller and power_meter to process
        estimated_step_delay = 0.15

        time_left = 0
        if progress == 0:
            time_left += SLEEP_STANDBY + SLEEP_INITIAL
        time_left += num_variations_left * (SLEEP_TIME + estimated_step_delay)
        if SAMPLE_COUNT > 1:
            time_left += num_variations_left * SAMPLE_COUNT * (SLEEP_TIME_SAMPLE + estimated_step_delay)

        if isinstance(current_variation, HsVariation):
            sat_steps_left = round((MAX_BRIGHTNESS - current_variation.bri) / HS_BRI_STEPS) - 1
            time_left += sat_steps_left * SLEEP_TIME_SAT
            hue_steps_left = round(MAX_HUE / HS_HUE_STEPS * sat_steps_left)
            time_left += hue_steps_left * SLEEP_TIME_HUE

        if isinstance(current_variation, ColorTempVariation):
            ct_steps_left = round((MAX_BRIGHTNESS - current_variation.bri) / CT_BRI_STEPS) - 1
            time_left += ct_steps_left * SLEEP_TIME_CT

        if time_left > 3600:
            formatted_time = f"{round(time_left / 3600, 1)}h"
        elif time_left > 60:
            formatted_time = f"{round(time_left / 60, 1)}m"
        else:
            formatted_time = f"{time_left}s"

        return formatted_time

    def write_model_json(
        self, directory: str, standby_power: float, name: str, measure_device: str
    ):
        json_data = json.dumps(
            {
                "measure_device": measure_device,
                "measure_method": "script",
                "measure_description": "Measured with utils/measure script",
                "measure_settings": {
                    "VERSION": _VERSION,
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
                    "message": "Which powermeter (manufacturer, model) do you use to take the measurement?",
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
                    "message": "How many lights are you measuring?",
                    "when": lambda answers: answers["multiple_lights"],
                },
            ]
            + self.light_controller.get_questions()
            + self.power_meter.get_questions()
        )

class CsvWriter:
    def __init__(self, csv_file: TextIOWrapper, color_mode: str, add_header: bool):
        self.csv_file = csv_file
        self.writer = csv.writer(csv_file)
        self.rows_written = 0
        if add_header:
            header_row = CSV_HEADERS[color_mode]
            if CSV_ADD_DATETIME_COLUMN:
                header_row.append("time")
            self.writer.writerow(header_row)
    
    def write_measurement(self, variation: Variation, power: float):
        row = variation.to_csv_row()
        row.append(power)
        if CSV_ADD_DATETIME_COLUMN:
            row.append(dt.now().strftime("%Y%m%d%H%M%S"))
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % CSV_WRITE_BUFFER == 1:
            self.csv_file.flush()
            _LOGGER.debug("Flushing CSV buffer")


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

    def dummy(self):
        return LightController()

    def create(self) -> LightController:
        factories = {
            LIGHT_CONTROLLER_DUMMY: self.dummy,
            LIGHT_CONTROLLER_HUE: self.hue,
            LIGHT_CONTROLLER_HASS: self.hass
        }
        factory = factories.get(SELECTED_LIGHT_CONTROLLER)
        if factory is None:
            raise Exception(f"Could not find a factory for {SELECTED_LIGHT_CONTROLLER}")

        _LOGGER.info(f"Selected Light controller: {SELECTED_LIGHT_CONTROLLER}")
        return factory()


class PowerMeterFactory:
    def dummy(self):
        return DummyPowerMeter()

    def hass(self):
        return HassPowerMeter(HASS_URL, HASS_TOKEN)

    def kasa(self):
        return KasaPowerMeter(KASA_DEVICE_IP)
    
    def manual(self):
        return ManualPowerMeter()

    def shelly(self):
        return ShellyPowerMeter(SHELLY_IP, SHELLY_TIMEOUT)

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
            POWER_METER_MANUAL: self.manual,
            POWER_METER_SHELLY: self.shelly,
            POWER_METER_TASMOTA: self.tasmota,
            POWER_METER_TUYA: self.tuya,
            POWER_METER_DUMMY: self.dummy
        }
        factory = factories.get(SELECTED_POWER_METER)
        if factory is None:
            raise PowerMeterError(f"Could not find a factory for {SELECTED_POWER_METER}")

        _LOGGER.info(f"Selected powermeter: {SELECTED_POWER_METER}")
        return factory()

def main():
    print(f"Powercalc measure: {_VERSION}\n")

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
