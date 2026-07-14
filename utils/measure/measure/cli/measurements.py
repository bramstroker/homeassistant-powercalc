from __future__ import annotations

from collections.abc import Callable

from inquirer.questions import Question  # type: ignore[import-untyped]

from measure.cli.environment import CliEnvironment
from measure.cli.questions import (
    average_questions,
    charging_questions,
    hass_charging_controller_questions,
    hass_fan_controller_questions,
    hass_light_controller_questions,
    hass_media_controller_questions,
    hass_power_meter_questions,
    hue_light_controller_questions,
    light_questions,
    recorder_questions,
    speaker_questions,
)
from measure.const import MeasureType
from measure.controller.charging.const import ChargingControllerType
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import LightControllerType
from measure.controller.media.const import MediaControllerType
from measure.powermeter.const import PowerMeterType

type CliQuestionBuilder = Callable[[CliEnvironment], list[Question]]


def _light(environment: CliEnvironment) -> list[Question]:
    controller_questions: list[Question] = []
    if environment.selected_light_controller == LightControllerType.HASS:
        controller_questions = hass_light_controller_questions()
    elif environment.selected_light_controller == LightControllerType.HUE:
        controller_questions = hue_light_controller_questions()
    supports_effects = environment.selected_light_controller != LightControllerType.HUE
    return light_questions(supports_effects=supports_effects) + controller_questions


def _speaker(environment: CliEnvironment) -> list[Question]:
    controller_questions = (
        hass_media_controller_questions() if environment.selected_media_controller == MediaControllerType.HASS else []
    )
    return controller_questions + speaker_questions()


def _recorder(_: CliEnvironment) -> list[Question]:
    return recorder_questions()


def _average(_: CliEnvironment) -> list[Question]:
    return average_questions()


def _charging(environment: CliEnvironment) -> list[Question]:
    controller_questions = (
        hass_charging_controller_questions()
        if environment.selected_charging_controller == ChargingControllerType.HASS
        else []
    )
    return charging_questions() + controller_questions


def _fan(environment: CliEnvironment) -> list[Question]:
    if environment.selected_fan_controller == FanControllerType.HASS:
        return hass_fan_controller_questions()
    return []


CLI_QUESTION_BUILDERS: dict[MeasureType, CliQuestionBuilder] = {
    MeasureType.LIGHT: _light,
    MeasureType.SPEAKER: _speaker,
    MeasureType.RECORDER: _recorder,
    MeasureType.AVERAGE: _average,
    MeasureType.CHARGING: _charging,
    MeasureType.FAN: _fan,
}


def measurement_questions(measure_type: MeasureType, environment: CliEnvironment) -> list[Question]:
    try:
        questions = CLI_QUESTION_BUILDERS[measure_type](environment)
    except KeyError as error:
        raise ValueError(f"No CLI question builder registered for {measure_type}") from error
    if environment.selected_power_meter == PowerMeterType.HASS:
        questions.extend(hass_power_meter_questions())
    return questions
