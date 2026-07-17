#!/usr/bin/env python3

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
from typing import Any, cast

import inquirer
from inquirer.errors import ValidationError
from inquirer.questions import Question
from inquirer.render import ConsoleRender

from measure.assembler import MeasurementAssembler
from measure.cli.dummy_load import (
    CliDummyLoadCalibrationStore,
    apply_dummy_load_answers,
    dummy_load_enabled_question,
    dummy_load_questions,
)
from measure.cli.environment import CliEnvironment
from measure.cli.interaction import ConsoleInteraction
from measure.cli.measurements import measurement_questions
from measure.cli.request_adapter import request_from_answers
from measure.const import (
    MEASURE_TYPE_LABELS,
    PROJECT_DIR,
    QUESTION_ENTITY_ID,
    QUESTION_GENERATE_MODEL_JSON,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODEL_ID,
    QUESTION_MODEL_NAME,
    MeasureType,
    parse_measure_type,
)
from measure.controller.charging.const import ChargingControllerType
from measure.controller.errors import ControllerError
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.media.const import MediaControllerType
from measure.execution import MeasurementExecution
from measure.home_assistant import HomeAssistantManager
from measure.home_assistant_entities import HomeAssistantEntityCatalog
from measure.powermeter.const import PowerMeterType
from measure.powermeter.errors import PowerMeterError
from measure.runner.const import QUESTION_MODE
from measure.runner.errors import RunnerError

with open(os.path.join(PROJECT_DIR, ".VERSION")) as f:
    _VERSION = f.read().strip()

config = CliEnvironment()

logging.basicConfig(
    level=logging.getLevelName(config.log_level),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_DIR, "measure.log")),
        logging.StreamHandler(),
    ],
)


MODEL_ID_EXAMPLES = {
    MeasureType.LIGHT: "LED1837R5",
    MeasureType.SPEAKER: "One SL",
    MeasureType.FAN: "AM07",
}

_LOGGER = logging.getLogger("measure")


class Measure:
    """Collect CLI input and dispatch one assembled measurement."""

    def __init__(
        self,
        config: CliEnvironment,
        console_render: ConsoleRender | None = None,
        dummy_load_calibration_store: CliDummyLoadCalibrationStore | None = None,
    ) -> None:
        self.measure_type: MeasureType = MeasureType.LIGHT
        self.console_render = console_render
        self.config = config
        self._model_id_defaults: dict[str, str | None] = {}
        self._home_assistant: HomeAssistantManager | None = None
        self._entity_catalog: HomeAssistantEntityCatalog | None = None
        self._dummy_load_calibration_store = dummy_load_calibration_store or CliDummyLoadCalibrationStore()

    def start(self) -> None:
        """Run the interactive wizard and dispatch the resulting request."""

        try:
            self._select_measure_type()
            self._log_selected_controllers()
            entity_catalog = self._home_assistant_entity_catalog() if self._uses_home_assistant() else None
            specific_questions = measurement_questions(self.measure_type, self.config, entity_catalog)
            answers = self.ask_questions(self.get_questions(specific_questions))
            interaction = ConsoleInteraction()
            request = request_from_answers(self.measure_type, answers, self.config)
            request = apply_dummy_load_answers(request, answers, self._dummy_load_calibration_store)
            if self._uses_home_assistant():
                self._home_assistant_manager()
            prepared = MeasurementAssembler(
                interaction,
                home_assistant=self._home_assistant,
                dummy_load_calibration_store=self._dummy_load_calibration_store,
                tuya_device_key=(
                    self.config.tuya_device_key if self.config.selected_power_meter == PowerMeterType.TUYA else None
                ),
            ).assemble(request)
            model_id = str(answers.get(QUESTION_MODEL_ID, "generic"))
            execution = MeasurementExecution(
                measurement=prepared,
                output_directory=Path(PROJECT_DIR) / "export" / model_id,
            )
            execution.run()
        finally:
            if self._home_assistant is not None:
                self._home_assistant.close()
            self._home_assistant = None
            self._entity_catalog = None

        if execution.output_directory is not None:
            _LOGGER.info(
                "Measurement session finished. Files exported to %s",
                execution.output_directory,
            )

    def _select_measure_type(self) -> None:
        if self.config.selected_measure_type:
            self.measure_type = parse_measure_type(self.config.selected_measure_type)
            return

        self.measure_type = inquirer.list_input(
            "What kind of measurement session do you want to run?",
            choices=[(MEASURE_TYPE_LABELS[kind], kind) for kind in MeasureType],
            render=self.console_render,
        )

    def _log_selected_controllers(self) -> None:
        _LOGGER.info("Selected powermeter: %s", self.config.selected_power_meter)
        if self.measure_type == MeasureType.LIGHT:
            _LOGGER.info("Selected light controller: %s", self.config.selected_light_controller)
        if self.measure_type == MeasureType.SPEAKER:
            _LOGGER.info("Selected media controller: %s", self.config.selected_media_controller)
        if self.measure_type == MeasureType.FAN:
            _LOGGER.info("Selected fan controller: %s", self.config.selected_fan_controller)

    def get_questions(self, specific_questions: list[Question]) -> list[Question]:
        """Combine common profile questions with measurement-specific questions."""
        if self.measure_type not in [MeasureType.AVERAGE, MeasureType.RECORDER]:
            entity_question_index = next(
                (index for index, question in enumerate(specific_questions) if question.name == QUESTION_ENTITY_ID),
                None,
            )
            questions_before_profile = (
                specific_questions[: entity_question_index + 1] if entity_question_index is not None else []
            )
            questions_after_profile = (
                specific_questions[entity_question_index + 1 :]
                if entity_question_index is not None
                else specific_questions
            )
            questions = [
                inquirer.Confirm(
                    name=QUESTION_GENERATE_MODEL_JSON,
                    message="Do you want to generate model.json?",
                    default=True,
                ),
                dummy_load_enabled_question(),
                *questions_before_profile,
                inquirer.Text(
                    name=QUESTION_MODEL_ID,
                    message=f"Specify the model id. e.g. {MODEL_ID_EXAMPLES.get(self.measure_type, 'LED1837R5')}",
                    default=self._default_model_id,
                    validate=validate_required,
                ),
                inquirer.Text(
                    name=QUESTION_MODEL_NAME,
                    message=f"Specify the full {self.measure_type} model name",
                    ignore=lambda answers: not answers.get(QUESTION_GENERATE_MODEL_JSON),
                    validate=validate_required,
                ),
                inquirer.Text(
                    name=QUESTION_MEASURE_DEVICE,
                    message="Which powermeter (manufacturer, model) do you use to take the measurement?",
                    ignore=lambda answers: not answers.get(QUESTION_GENERATE_MODEL_JSON),
                    validate=validate_required,
                ),
                *questions_after_profile,
            ]
        else:
            questions = [dummy_load_enabled_question(), *specific_questions]

        return [
            *questions,
            *dummy_load_questions(self.measure_type, self.config, self._dummy_load_calibration_store)[1:],
        ]

    def _default_model_id(self, answers: dict[str, Any]) -> str | None:
        entity_id = str(answers.get(QUESTION_ENTITY_ID, "")).strip()
        if not entity_id:
            return None
        if entity_id not in self._model_id_defaults:
            try:
                entity = self._home_assistant_entity_catalog().load_snapshot().get(entity_id)
                self._model_id_defaults[entity_id] = entity.model_id if entity is not None else None
            except Exception as error:  # noqa: BLE001 - prefill is optional; manual input remains available
                _LOGGER.warning("Could not prefill model ID for %s: %s", entity_id, error)
                self._model_id_defaults[entity_id] = None
        return self._model_id_defaults[entity_id]

    def _home_assistant_manager(self) -> HomeAssistantManager:
        if self._home_assistant is None:
            self._home_assistant = HomeAssistantManager(self.config.hass_url, self.config.hass_token)
        return self._home_assistant

    def _home_assistant_entity_catalog(self) -> HomeAssistantEntityCatalog:
        if self._entity_catalog is None:
            self._entity_catalog = HomeAssistantEntityCatalog(self._home_assistant_manager())
        return self._entity_catalog

    def _uses_home_assistant(self) -> bool:
        return (
            self.config.selected_power_meter == PowerMeterType.HASS
            or (
                self.measure_type == MeasureType.LIGHT
                and self.config.selected_light_controller == LightControllerType.HASS
            )
            or (
                self.measure_type == MeasureType.SPEAKER
                and self.config.selected_media_controller == MediaControllerType.HASS
            )
            or (
                self.measure_type == MeasureType.CHARGING
                and self.config.selected_charging_controller == ChargingControllerType.HASS
            )
            or (self.measure_type == MeasureType.FAN and self.config.selected_fan_controller == FanControllerType.HASS)
        )

    def ask_questions(self, questions: list[Question]) -> dict[str, Any]:
        """Apply environment overrides and prompt for the remaining answers."""

        # Only ask questions which answers are not predefined in .env file
        questions_to_ask = list(questions)

        predefined_answers: dict[str, Any] = {}
        for question in questions:
            question_name = str(question.name)
            env_var = question_name.upper()
            conf_value = self.config.get_conf_value(env_var)
            if conf_value is not None:
                answer_value: Any = conf_value
                if isinstance(question, inquirer.Confirm):
                    answer_value = str_to_bool(conf_value)
                predefined_answers[question_name] = answer_value
                questions_to_ask.remove(question)

        answers = cast(
            dict[str, Any],
            inquirer.prompt(questions_to_ask, answers=predefined_answers, render=self.console_render),
        )
        answers.update(predefined_answers)

        if QUESTION_MODE in answers and not isinstance(answers[QUESTION_MODE], set):
            answers[QUESTION_MODE] = {LutMode(answers[QUESTION_MODE])}

        _LOGGER.debug("Answers: %s", answers)

        return answers


def validate_required(_: Any, val: str) -> bool:  # noqa: ANN401
    if len(val) == 0:
        raise ValidationError(
            "",
            reason="This question cannot be empty, please put in a value",
        )
    return True


def str_to_bool(value: Any) -> bool:  # noqa: ANN401
    if not value:
        return False
    return str(value).lower() in ("y", "yes", "t", "true", "on", "1")


def main() -> None:
    print(f"Powercalc measure: {_VERSION}\n")

    try:
        Measure(config).start()
        sys.exit(0)
    except KeyboardInterrupt:
        print("Aborted")
        sys.exit(1)
    except PowerMeterError, ControllerError, RunnerError:
        _LOGGER.exception("Aborting")
        sys.exit(1)


if __name__ == "__main__":
    main()
