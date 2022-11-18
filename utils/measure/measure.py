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
from enum import Enum
from io import TextIOWrapper
from typing import Any, Iterator, Optional

import inquirer
import config
from decouple import config as decouple_config
from decouple import UndefinedValueError
from inquirer.errors import ValidationError
from inquirer.questions import Question
from light_controller.controller import LightController
from light_controller.factory import LightControllerFactory
from light_controller.errors import LightControllerError
from powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from powermeter.powermeter import PowerMeter, PowerMeasurementResult
from powermeter.factory import PowerMeterFactory
from runner.runner import MeasurementRunner
from runner.light import LightRunner
from runner.speaker import SpeakerRunner
from measure_util import MeasureUtil

logging.basicConfig(
    level=logging.getLevelName(config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(sys.path[0], "measure.log")),
        logging.StreamHandler()
    ]
)


class DeviceType(str, Enum):
    """Type of devices to measure power of"""

    LIGHT = "Light bulb(s)"
    SPEAKER = "Smart speaker"


_LOGGER = logging.getLogger("measure")

with open(os.path.join(sys.path[0], ".VERSION"), "r") as f:
    _VERSION = f.read().strip()


class Measure:
    """Measure the power usage of a light.

    This class is responsible for measuring the power usage of a light. It uses a LightController to control the light, and a PowerMeter
    to measure the power usage. The measurements are exported as CSV files in export/<model_id>/<color_mode>.csv (or .csv.gz). The
    model_id is retrieved from the LightController and color mode can be selected by user input or config file (.env). The CSV files
    contain one row per variation, where each column represents one property of that variation (e.g., brightness, hue, saturation). The last
    column contains the measured power value in watt.
    If you want to generate model JSON files for the LUT model, you can do so by answering yes to the question "Do you want to generate
    model.json?".

    Example
    -------
    
    >>> from light_controller import LightController
    >>> from power_meter import PowerMeter

    >>> light_controller = LightController()
    >>> power_meter = PowerMeter()

    >>> measure = Measure(light_controller, power_meter)
    >>> measure.start()

    # CSV file export/<model-id>/hs.csv will be created with measurements for HS
    color mode (e.g., hue and saturation). The last column contains the measured
    power value in watt.

    # If you answered yes to generating a model JSON file, a model.json will be
    created in export/<model-id>
    
    """

    def __init__(self, power_meter: PowerMeter) -> None:
        """This class measures the power consumption of the light bulb.

        Parameters
        ----------
        light_controller : LightController
            The light controller to use.
        power_meter : PowerMeter
            The power meter to use.
        """
        self.measure_util = MeasureUtil()
        self.power_meter = power_meter
        self.runner: MeasurementRunner | None = None

    def start(self) -> None:
        """Starts the measurement session.

        This method asks the user for the required information, sets up the light controller and power meter and starts the measurement
        session.

        Raises
        ------
        PowerMeterError
            If the power meter is not connected.

        ZeroReadingError
            If the power meter returns a 0 reading.

        Notes
        -----
        This method is the main entry point for the measurement
        session.

        Examples
        --------
        >>> measure = Measure()
        >>> measure.start()
        """

        _LOGGER.info(f"Selected powermeter: {config.SELECTED_POWER_METER}")
        if DeviceType.LIGHT:
            _LOGGER.info(f"Selected light controller: {config.SELECTED_LIGHT_CONTROLLER}")

        device = inquirer.list_input("What kind of device do you want to measure the power of?",
                                     choices=[cls.value for cls in DeviceType])
        self.runner = RunnerFactory().create_runner(device)

        answers = self.ask_questions()
        self.power_meter.process_answers(answers)

        self.runner.prepare()
        self.runner.run(answers)

        # if answers["generate_model_json"] and not resume_at:
        #     try:
        #         standby_power = self.measure_standby_power()
        #     except PowerMeterError as error:
        #         _LOGGER.error(f"Aborting: {error}")
        #         return
        #
        #     self.write_model_json(
        #         directory=export_directory,
        #         standby_power=standby_power,
        #         name=answers["model_name"],
        #         measure_device=answers["measure_device"],
        #     )

    @staticmethod
    def write_model_json(
            directory: str, standby_power: float, name: str, measure_device: str
    ):
        """Write model.json manifest file"""
        json_data = json.dumps(
            {
                "measure_device": measure_device,
                "measure_method": "script",
                "measure_description": "Measured with utils/measure script",
                "measure_settings": {
                    "VERSION": _VERSION,
                    "SAMPLE_COUNT": config.SAMPLE_COUNT,
                    "SLEEP_TIME": config.SLEEP_TIME
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
            inquirer.Confirm(
                name="generate_model_json",
                message="Do you want to generate model.json?",
                default=True
            ),
            # Todo don't call light anymore
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
        ]

        questions.extend(self.runner.get_questions())
        questions.extend(self.power_meter.get_questions())

        return questions

    def ask_questions(self) -> dict[str, Any]:
        """Ask question and return a dictionary with the answers"""
        all_questions = self.get_questions()

        # Only ask questions which answers are not predefined in .env file
        questions_to_ask = [question for question in all_questions if not config_key_exists(str(question.name).upper())]

        predefined_answers = {}
        for question in all_questions:
            question_name = str(question.name)
            env_var = question_name.upper()
            if config_key_exists(env_var):
                conf_value = decouple_config(env_var)
                if isinstance(question, inquirer.Confirm):
                    conf_value = bool(str_to_bool(conf_value))
                predefined_answers[question_name] = conf_value

        answers = inquirer.prompt(questions_to_ask, answers=predefined_answers)

        _LOGGER.debug("Answers: %s", answers)

        return answers


def config_key_exists(key: str) -> bool:
    """Check whether a certain configuration exists in dot env file"""
    try:
        decouple_config(key)
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


class RunnerFactory:
    @staticmethod
    def create_runner(device_type: DeviceType) -> MeasurementRunner:
        if device_type == DeviceType.LIGHT:
            return LightRunner()
        if device_type == DeviceType.SPEAKER:
            return SpeakerRunner()


def main():
    print(f"Powercalc measure: {_VERSION}\n")

    try:
        power_meter = PowerMeterFactory().create()

        measure = Measure(power_meter)
        measure_util = MeasureUtil()

        args = sys.argv[1:]
        if len(args) > 0:
            if args[0] == "average":
                try:
                    duration = int(args[1])
                except IndexError:
                    duration = 60
                measure_util.take_average_measurement(duration)
                exit(0)

        measure.start()
        exit(0)
    except (PowerMeterError, LightControllerError) as e:
        _LOGGER.error(f"Aborting: {e}")
        exit(1)


if __name__ == "__main__":
    main()
