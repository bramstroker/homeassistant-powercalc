from __future__ import annotations

import csv
import gzip
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime as dt
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Iterator, Optional

import inquirer
from decouple import Choices, UndefinedValueError, config
from inquirer.errors import ValidationError
from inquirer.questions import Question
from light_controller.const import MODE_BRIGHTNESS, MODE_COLOR_TEMP, MODE_HS
from light_controller.controller import LightController
from light_controller.errors import LightControllerError
from light_controller.hass import HassLightController
from light_controller.hue import HueLightController
from powermeter.dummy import DummyPowerMeter
from powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from powermeter.hass import HassPowerMeter
from powermeter.kasa import KasaPowerMeter
from powermeter.manual import ManualPowerMeter
from powermeter.ocr import OcrPowerMeter
from powermeter.powermeter import PowerMeter
from powermeter.shelly import ShellyPowerMeter
from powermeter.tasmota import TasmotaPowerMeter
from powermeter.tuya import TuyaPowerMeter

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
MIN_SAT = min(max(config("MIN_SAT", default=1, cast=int), 1), 255)
MAX_SAT = min(max(config("MAX_SAT", default=255, cast=int), 1), 255)
MIN_HUE = min(max(config("MIN_HUE", default=1, cast=int), 1), 65535)
MAX_HUE = min(max(config("MAX_HUE", default=65535, cast=int), 1), 65535)
CT_BRI_STEPS = min(config("CT_BRI_STEPS", default=5, cast=int), 10)
CT_MIRED_STEPS = min(config("CT_MIRED_STEPS", default=10, cast=int), 10)
BRI_BRI_STEPS = 1

HS_BRI_PRECISION = config("HS_BRI_PRECISION", default=1, cast=float)
HS_BRI_PRECISION = min(HS_BRI_PRECISION, 4)
HS_BRI_PRECISION = max(HS_BRI_PRECISION, 0.5)
HS_BRI_STEPS = round(32 / HS_BRI_PRECISION)
del HS_BRI_PRECISION

HS_HUE_PRECISION = config("HS_HUE_PRECISION", default=1, cast=float)
HS_HUE_PRECISION = min(HS_HUE_PRECISION, 4)
HS_HUE_PRECISION = max(HS_HUE_PRECISION, 0.5)
HS_HUE_STEPS = round(2731 / HS_HUE_PRECISION)
del HS_HUE_PRECISION

HS_SAT_PRECISION = config("HS_SAT_PRECISION", default=1, cast=float)
HS_SAT_PRECISION = min(HS_SAT_PRECISION, 4)
HS_SAT_PRECISION = max(HS_SAT_PRECISION, 0.5)
HS_SAT_STEPS = round(32 / HS_SAT_PRECISION)
del HS_SAT_PRECISION

POWER_METER_DUMMY = "dummy"
POWER_METER_HASS = "hass"
POWER_METER_KASA = "kasa"
POWER_METER_MANUAL = "manual"
POWER_METER_OCR = "ocr"
POWER_METER_SHELLY = "shelly"
POWER_METER_TASMOTA = "tasmota"
POWER_METER_TUYA = "tuya"
POWER_METERS = [
    POWER_METER_DUMMY,
    POWER_METER_HASS,
    POWER_METER_KASA,
    POWER_METER_MANUAL,
    POWER_METER_OCR,
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
SLEEP_TIME_NUDGE = config("SLEEP_TIME_NUDGE", default=10, cast=float)
PULSE_TIME_NUDGE = config("PULSE_TIME_NUDGE", default=2, cast=float)
MAX_RETRIES = config("MAX_RETRIES", default=5, cast=int)
MAX_NUDGES = config("MAX_NUDGES", default=0, cast=int)
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
HASS_CALL_UPDATE_ENTITY_SERVICE = config("HASS_CALL_UPDATE_ENTITY_SERVICE", default=False, cast=bool)
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
        """Starts the measurement session"""
        answers = self.ask_questions()
        self.light_controller.process_answers(answers)
        self.power_meter.process_answers(answers)
        self.color_mode = answers["color_mode"]
        self.num_lights = int(answers.get("num_lights") or 1)
        self.is_dummy_load_connected = bool(answers.get("dummy_load"))
        if self.is_dummy_load_connected:
            self.dummy_load_value = self.get_dummy_load_value()
            _LOGGER.info(f"Using {self.dummy_load_value}W as dummy load value")

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
            _LOGGER.info("Resuming measurements")
            resume_at = self.get_resume_variation(csv_file_path)
            file_write_mode = "a"
            write_header_row = False

        variations = list(self.get_variations(self.color_mode, resume_at))
        num_variations = len(variations)

        _LOGGER.info(f"Starting measurements. Estimated duration: {self.calculate_time_left(variations, variations[0])}")

        if answers["generate_model_json"] and not resume_at:
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

            if resume_at is None:
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
                except OutdatedMeasurementError as error:
                    self.nudge_and_remeasure(self.color_mode, variation)
                except ZeroReadingError as error:
                    self.num_0_readings += 1
                    _LOGGER.warning(f"Discarding measurement: {error}")
                    if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                        _LOGGER.error("Aborting measurement session. Received too many 0 readings")
                        return
                    continue
                except PowerMeterError as error:
                    _LOGGER.error(f"Aborting: {error}")
                    return
                _LOGGER.info(f"Measured power: {power}")
                csv_writer.write_measurement(variation, power)

            csv_file.close()
            _LOGGER.info(f"Hooray! measurements finished. Exported CSV file {csv_file_path}")

        if bool(answers.get("gzip", True)):
            self.gzip_csv(csv_file_path)
    def nudge_and_remeasure(self, color_mode: str, variation: Variation):
        for nudge_count in range(MAX_NUDGES):
            try:
                # Likely not significant enough change for PM to detect. Try nudging it
                _LOGGER.warning("Measurement is stuck, Nudging")
                # If brightness is low, set brightness high. Else, turn light off
                self.light_controller.change_light_state(MODE_BRIGHTNESS, on=(variation.bri < 128), bri=255)
                time.sleep(PULSE_TIME_NUDGE)
                variation_start_time = time.time()
                self.light_controller.change_light_state(
                    color_mode, on=True, **asdict(variation)
                )
                # Wait a longer amount of time for the PM to settle
                time.sleep(SLEEP_TIME_NUDGE)
                power = self.take_power_measurement(variation_start_time)
                return power
            except OutdatedMeasurementError:
                continue
            except ZeroReadingError as error:
                self.num_0_readings += 1
                _LOGGER.warning(f"Discarding measurement: {error}")
                if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                    _LOGGER.error("Aborting measurement session. Received too many 0 readings")
                    return
                continue
        raise OutdatedMeasurementError(f"Power measurement is outdated. Aborting after {nudge_count + 1} nudged retries")

    def should_resume(self, csv_file_path: str) -> bool:
        """Check whether we are able to resume a previous measurement session"""
        if not os.path.exists(csv_file_path):
            return False
        
        size = os.path.getsize(csv_file_path) 
        if size == 0:
            return False
        
        with open(csv_file_path, "r") as csv_file:
            rows = csv.reader(csv_file)
            if len(list(rows)) == 1:
                return False 

        try:
            return config("RESUME", cast=bool)
        except UndefinedValueError:
            return inquirer.confirm(
                message="CSV File already exists. Do you want to resume measurements?",
                default=True
            )


    def get_resume_variation(self, csv_file_path: str) -> Variation:
        """Determine the variation where we have to resume the measurements"""
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
        """Request a power reading from the configured power meter"""
        measurements = []
        # Take multiple samples to reduce noise
        for i in range(1, SAMPLE_COUNT + 1):
            _LOGGER.debug(f"Taking sample {i}")
            error = None
            try:
                measurement = self.power_meter.get_power()
                updated_at = dt.fromtimestamp(measurement.updated).strftime("%d-%m-%Y, %H:%M:%S")
                _LOGGER.debug(f"Measurement received (update_time={updated_at})")
            except PowerMeterError as err:
                error = err

            # Check if measurement is not outdated
            if measurement.updated < start_timestamp:
                error = OutdatedMeasurementError(f"Power measurement is outdated. Aborting after {MAX_RETRIES} successive retries")

            # Check if we not have a 0 measurument
            if measurement.power == 0:
                error = ZeroReadingError("0 watt was read from the power meter")

            if error:
                # Prevent endless recursion. Throw error when max retries is reached
                if retry_count == MAX_RETRIES:
                    raise error
                retry_count += 1
                time.sleep(SLEEP_TIME)
                self.take_power_measurement(start_timestamp, retry_count)

            measurements.append(measurement.power)
            if SAMPLE_COUNT > 1:
                time.sleep(SLEEP_TIME_SAMPLE)

        value = sum(measurements) / len(measurements) / self.num_lights
        if self.is_dummy_load_connected:
            value = value - self.dummy_load_value

        return round(value, 2)

    def gzip_csv(self, csv_file_path: str):
        """Gzip the CSV file"""
        with open(csv_file_path, "rb") as csv_file:
            with gzip.open(f"{csv_file_path}.gz", "wb") as gzip_file:
                shutil.copyfileobj(csv_file, gzip_file)


    def measure_standby_power(self) -> float:
        """Measures the standby power (when the light is OFF)"""
        self.light_controller.change_light_state(MODE_BRIGHTNESS, on=False)
        start_time = time.time()
        _LOGGER.info(f"Measuring standby power. Waiting for {SLEEP_STANDBY} seconds...")
        time.sleep(SLEEP_STANDBY)
        try:
            return self.take_power_measurement(start_time)
        except OutdatedMeasurementError as error:
            self.nudge_and_remeasure(MODE_BRIGHTNESS, Variation(0))
        except ZeroReadingError:
            _LOGGER.error("Measured 0 watt as standby usage, continuing now, but you probably need to have a look into measuring multiple lights at the same time or using a dummy load.")
            return 0

    def get_variations(self, color_mode: str, resume_at: Optional[Variation] = None) -> Iterator[Variation]:
        """Get all the light settings where the measure script needs to cycle through"""
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
        """Get color_temp variations"""
        min_mired = round(self.light_info.min_mired)
        max_mired = round(self.light_info.max_mired)
        for bri in self.inclusive_range(MIN_BRIGHTNESS, MAX_BRIGHTNESS, CT_BRI_STEPS):
            for mired in self.inclusive_range(min_mired, max_mired, CT_MIRED_STEPS):
                yield ColorTempVariation(bri=bri, ct=mired)

    def get_hs_variations(self) -> Iterator[HsVariation]:
        """Get hue/sat variations"""
        for bri in self.inclusive_range(MIN_BRIGHTNESS, MAX_BRIGHTNESS, HS_BRI_STEPS):
            for sat in self.inclusive_range(MIN_SAT, MAX_SAT, HS_SAT_STEPS):
                for hue in self.inclusive_range(MIN_HUE, MAX_HUE, HS_HUE_STEPS):
                    yield HsVariation(bri=bri, hue=hue, sat=sat)

    def get_brightness_variations(self) -> Iterator[Variation]:
        """Get brightness variations"""
        for bri in self.inclusive_range(MIN_BRIGHTNESS, MAX_BRIGHTNESS, BRI_BRI_STEPS):
            yield Variation(bri=bri)

    def inclusive_range(self, start: int, end: int, step: int) -> Iterator[int]:
        """Get an iterator including the min and max, with steps in between"""
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
        """Write model.json manifest file"""
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
    

    def get_questions(self) -> list[Question]:
        """Build list of questions to ask"""
        questions = [
            inquirer.List(
                name="color_mode",
                message="Select the color mode",
                choices=[MODE_HS, MODE_COLOR_TEMP, MODE_BRIGHTNESS],
                default=MODE_HS
            ),
            inquirer.Confirm(
                name="generate_model_json",
                message="Do you want to generate model.json?",
                default=True
            ),
            inquirer.Text(
                name="model_name",
                message="Specify the full light model name",
                ignore=lambda answers: not answers.get("generate_model_json"),
                validate=validate_required,
            ),
            inquirer.Text(
                name="measure_device",
                message="Which powermeter (manufacturer, model) do you use to take the measurement?",
                ignore=lambda answers: not answers.get("generate_model_json"),
                validate=validate_required,
            ),
            inquirer.Confirm(
                name="gzip",
                message="Do you want to gzip CSV files?",
                default=True
            ),
            inquirer.Confirm(
                name="dummy_load",
                message="Did you connect a dummy load? This can help to be able to measure standby power and low brightness levels correctly",
                default=False
            ),
            inquirer.Confirm(
                name="multiple_lights",
                message="Are you measuring multiple lights. In some situations it helps to connect multiple lights to be able to measure low currents.",
                default=False
            ),
            inquirer.Text(
                name="num_lights",
                message="How many lights are you measuring?",
                ignore=lambda answers: not answers.get("multiple_lights"),
                validate=lambda _, current: re.match('\d+', current),
            ),
        ]

        questions.extend(self.light_controller.get_questions())
        questions.extend(self.power_meter.get_questions())

        return questions

    
    def ask_questions(self) -> dict[str, Any]:
        """Ask question and return a dictionary with the answers"""
        all_questions = self.get_questions()

        #Only ask questions which answers are not predefined in .env file
        questions_to_ask = [question for question in all_questions if not config_key_exists(str(question.name).upper())]

        predefined_answers = {}
        for question in all_questions:
            question_name = str(question.name)
            env_var = question_name.upper()
            if config_key_exists(env_var):
                conf_value = config(env_var)
                if isinstance(question, inquirer.Confirm):
                    conf_value = bool(str_to_bool(conf_value))
                predefined_answers[question_name] = conf_value

        answers = inquirer.prompt(questions_to_ask, answers=predefined_answers)

        _LOGGER.debug("Answers: %s", answers)

        return answers
    
    def get_dummy_load_value(self) -> float:
        """Get the previously measured dummy load value"""

        dummy_load_file = os.path.join(Path(__file__).parent.absolute(), ".persistent/dummy_load")
        if not os.path.exists(dummy_load_file):
            return self.measure_dummy_load(dummy_load_file)

        with open(dummy_load_file, "r") as f:
            return float(f.read())
    
    def measure_dummy_load(self, file_path: str) -> float:
        """Measure the dummy load and persist the value for future measurement session"""
        input("Only connect your dummy load to your smart plug, not the light! Press enter to start measuring the dummy load..")
        values = []
        for i in range(1):
            result = self.power_meter.get_power()
            values.append(result.power)
            _LOGGER.info(f"Dummy load watt: {result.power}")
            time.sleep(SLEEP_TIME)
        average = sum(values) / len(values)

        with open(file_path, "w") as f:
            f.write(str(average))

        input("Connect your light now and press enter to start measuring..")
        return average

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
        """Write row with measurement to the CSV"""
        row = variation.to_csv_row()
        row.append(power)
        if CSV_ADD_DATETIME_COLUMN:
            row.append(dt.now().strftime("%Y%m%d%H%M%S"))
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % CSV_WRITE_BUFFER == 1:
            self.csv_file.flush()
            _LOGGER.debug("Flushing CSV buffer")


def config_key_exists(key: str) -> bool:
    """Check whether a certain configuration exists in dot env file"""
    try:
        config(key)
        return True
    except UndefinedValueError:
        return False

def validate_required(_, val):
    """Validation function for the inquirer question, checks if the input has a not empty value"""
    if len(val) == 0:
        raise ValidationError("", reason="This question cannot be empty, please put in a value")
    return True

def str_to_bool(value: Any) -> bool:
    """Return whether the provided string (or any value really) represents true."""
    if not value:
        return False
    return str(value).lower() in ("y", "yes", "t", "true", "on", "1")

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
        """Create the light controller object"""
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
        return HassPowerMeter(HASS_URL, HASS_TOKEN, HASS_CALL_UPDATE_ENTITY_SERVICE)

    def kasa(self):
        return KasaPowerMeter(KASA_DEVICE_IP)
    
    def manual(self):
        return ManualPowerMeter()
    
    def ocr(self):
        return OcrPowerMeter()

    def shelly(self):
        return ShellyPowerMeter(SHELLY_IP, SHELLY_TIMEOUT)

    def tasmota(self):
        return TasmotaPowerMeter(TASMOTA_DEVICE_IP)

    def tuya(self):
        return TuyaPowerMeter(
            TUYA_DEVICE_ID, TUYA_DEVICE_IP, TUYA_DEVICE_KEY, TUYA_DEVICE_VERSION
        )

    def create(self) -> PowerMeter:
        """Create the power meter object"""
        factories = {
            POWER_METER_HASS: self.hass,
            POWER_METER_KASA: self.kasa,
            POWER_METER_MANUAL: self.manual,
            POWER_METER_OCR: self.ocr,
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
        light_controller = light_controller_factory.create()
    
        measure = Measure(light_controller, power_meter)
        measure.start()
    except (PowerMeterError, LightControllerError) as e:
        _LOGGER.error(f"Aborting: {e}")
        exit(1)

if __name__ == "__main__":
    main()
