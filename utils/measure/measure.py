from __future__ import annotations

import json
import logging
import os
import sys
from enum import Enum
from typing import Any

import config
import inquirer
from decouple import UndefinedValueError
from decouple import config as decouple_config
from inquirer.errors import ValidationError
from inquirer.questions import Question
from light_controller.errors import LightControllerError
from measure_util import MeasureUtil
from powermeter.errors import PowerMeterError
from powermeter.factory import PowerMeterFactory
from powermeter.powermeter import PowerMeter
from runner.light import LightRunner
from runner.runner import MeasurementRunner
from runner.speaker import SpeakerRunner

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

logging.basicConfig(
    level=logging.getLevelName(config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(sys.path[0], "measure.log")),
        logging.StreamHandler(),
    ],
)


class DeviceType(str, Enum):
    """Type of devices to measure power of"""

    LIGHT = "Light bulb(s)"
    SPEAKER = "Smart speaker"


_LOGGER = logging.getLogger("measure")

with open(os.path.join(sys.path[0], ".VERSION"), "r") as f:
    _VERSION = f.read().strip()


class Measure:
    """
    Main class to measure the power usage of a device.

    If you answered yes to generating a model JSON file, a model.json will be created in export/<model-id>
    """

    def __init__(self, power_meter: PowerMeter) -> None:
        """This class measures the power consumption of a device.

        Parameters
        ----------
        power_meter : PowerMeter
            The power meter to use.
        """
        self.power_meter = power_meter
        self.runner: MeasurementRunner | None = None
        self.device_type: DeviceType = DeviceType.LIGHT

    def start(self) -> None:
        """Starts the measurement session.

        This method asks the user for the required information, sets up the runner and power meter and starts the measurement
        session.

        Notes
        -----
        This method is the main entry point for the measurement
        session.
        It selects a runner based on the selected device type
        This runner is responsible for executing the measurement session for the given device type

        Examples
        --------
        >>> measure = Measure()
        >>> measure.start()
        """

        _LOGGER.info(f"Selected powermeter: {config.SELECTED_POWER_METER}")
        if DeviceType.LIGHT:
            _LOGGER.info(
                f"Selected light controller: {config.SELECTED_LIGHT_CONTROLLER}"
            )

        if config.SELECTED_DEVICE_TYPE:
            self.device_type = DeviceType(config.SELECTED_DEVICE_TYPE)
        else:
            self.device_type = inquirer.list_input(
                "What kind of device do you want to measure the power of?",
                choices=[cls.value for cls in DeviceType],
            )

        self.runner = RunnerFactory().create_runner(self.device_type, self.power_meter)
        
        answers = self.ask_questions(self.get_questions())
        self.power_meter.process_answers(answers)
        self.runner.prepare(answers)

        export_directory = os.path.join(
            os.path.dirname(__file__), "export", self.runner.get_export_directory()
        )
        if not os.path.exists(export_directory):
            os.makedirs(export_directory)

        runner_result = self.runner.run(answers, export_directory)
        if not runner_result:
            _LOGGER.error("Some error occured during the measurement session")

        generate_model_json: bool = (
            answers["generate_model_json"]
            and not runner_result.skip_model_json_generation
        )

        if generate_model_json:
            try:
                standby_power = self.runner.measure_standby_power()
            except PowerMeterError as error:
                _LOGGER.error(f"Aborting: {error}")
                return

            self.write_model_json(
                directory=export_directory,
                standby_power=standby_power,
                name=answers["model_name"],
                measure_device=answers["measure_device"],
                extra_json_data=runner_result.model_json_data,
            )

        if generate_model_json or isinstance(self.runner, LightRunner):
            _LOGGER.info(
                f"Measurement session finished. Files exported to {export_directory}"
            )

    @staticmethod
    def write_model_json(
        directory: str,
        standby_power: float,
        name: str,
        measure_device: str,
        extra_json_data: dict | None = None,
    ):
        """Write model.json manifest file"""
        json_data = {
            "measure_device": measure_device,
            "measure_method": "script",
            "measure_description": "Measured with utils/measure script",
            "measure_settings": {
                "VERSION": _VERSION,
                "SAMPLE_COUNT": config.SAMPLE_COUNT,
                "SLEEP_TIME": config.SLEEP_TIME,
            },
            "name": name,
            "standby_power": standby_power,
        }
        if extra_json_data:
            json_data.update(extra_json_data)

        json_string = json.dumps(
            json_data,
            indent=4,
            sort_keys=True,
        )
        json_file = open(os.path.join(directory, "model.json"), "w")
        json_file.write(json_string)
        json_file.close()

    def get_questions(self) -> list[Question]:
        """
        Build list of questions to ask.
        Returns generic questions which are asked regardless of the choosen device type
        Additionally the configured runner and power_meter can also provide further questions
        """
        questions = [
            inquirer.Confirm(
                name="generate_model_json",
                message="Do you want to generate model.json?",
                default=True,
            ),
            inquirer.Text(
                name="model_name",
                message=f"Specify the full {self.device_type} model name",
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

    @staticmethod
    def ask_questions(questions: list[Question]) -> dict[str, Any]:
        """
        Ask question and return a dictionary with the answers.
        It will also check if any predefined answers are defined in .env, and will skip asking these
        """

        # Only ask questions which answers are not predefined in .env file
        questions_to_ask = [
            question
            for question in questions
            if not config_key_exists(str(question.name).upper())
        ]

        predefined_answers = {}
        for question in questions:
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
        raise ValidationError(
            "", reason="This question cannot be empty, please put in a value"
        )
    return True


def str_to_bool(value: Any) -> bool:
    """Return whether the provided string (or any value really) represents true."""
    if not value:
        return False
    return str(value).lower() in ("y", "yes", "t", "true", "on", "1")


class RunnerFactory:
    @staticmethod
    def create_runner(device_type: DeviceType, power_meter: PowerMeter) -> MeasurementRunner:
        """Creates a runner instance based on selected device type"""
        measure_util = MeasureUtil(power_meter)
        if device_type == DeviceType.LIGHT:
            return LightRunner(measure_util)
        if device_type == DeviceType.SPEAKER:
            return SpeakerRunner(measure_util)


def main():
    print(f"Powercalc measure: {_VERSION}\n")

    try:
        power_meter = PowerMeterFactory().create()

        measure = Measure(power_meter)
        measure_util = MeasureUtil(power_meter)

        args = sys.argv[1:]
        if len(args) > 0:
            if args[0] == "average":
                try:
                    duration = int(args[1])
                except IndexError:
                    duration = 60
                questions = power_meter.get_questions()
                if questions:
                    answers = measure.ask_questions(questions)
                    power_meter.process_answers(answers)
                measure_util.take_average_measurement(duration)
                exit(0)

        measure.start()
        exit(0)
    except (PowerMeterError, LightControllerError) as e:
        _LOGGER.error(f"Aborting: {e}")
        exit(1)


if __name__ == "__main__":
    main()
