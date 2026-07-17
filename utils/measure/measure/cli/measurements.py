from __future__ import annotations

from collections.abc import Callable

from inquirer.questions import Question

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
from measure.home_assistant_entities import HomeAssistantEntityCatalog
from measure.powermeter.const import PowerMeterType

type CliQuestionBuilder = Callable[[CliEnvironment, HomeAssistantEntityCatalog | None], list[Question]]


def _require_entity_catalog(entity_catalog: HomeAssistantEntityCatalog | None) -> HomeAssistantEntityCatalog:
    if entity_catalog is None:
        raise ValueError("Home Assistant entity choices require an entity catalog")
    return entity_catalog


def _light(environment: CliEnvironment, entity_catalog: HomeAssistantEntityCatalog | None) -> list[Question]:
    controller_questions: list[Question] = []
    if environment.selected_light_controller == LightControllerType.HASS:
        controller_questions = hass_light_controller_questions(_require_entity_catalog(entity_catalog))
    elif environment.selected_light_controller == LightControllerType.HUE:
        controller_questions = hue_light_controller_questions()
    supports_effects = environment.selected_light_controller != LightControllerType.HUE
    return light_questions(supports_effects=supports_effects) + controller_questions


def _speaker(environment: CliEnvironment, entity_catalog: HomeAssistantEntityCatalog | None) -> list[Question]:
    controller_questions = (
        hass_media_controller_questions(_require_entity_catalog(entity_catalog))
        if environment.selected_media_controller == MediaControllerType.HASS
        else []
    )
    return controller_questions + speaker_questions()


def _recorder(_: CliEnvironment, __: HomeAssistantEntityCatalog | None) -> list[Question]:
    return recorder_questions()


def _average(_: CliEnvironment, __: HomeAssistantEntityCatalog | None) -> list[Question]:
    return average_questions()


def _charging(environment: CliEnvironment, entity_catalog: HomeAssistantEntityCatalog | None) -> list[Question]:
    controller_questions = (
        hass_charging_controller_questions(_require_entity_catalog(entity_catalog))
        if environment.selected_charging_controller == ChargingControllerType.HASS
        else []
    )
    return charging_questions() + controller_questions


def _fan(environment: CliEnvironment, entity_catalog: HomeAssistantEntityCatalog | None) -> list[Question]:
    if environment.selected_fan_controller == FanControllerType.HASS:
        return hass_fan_controller_questions(_require_entity_catalog(entity_catalog))
    return []


CLI_QUESTION_BUILDERS: dict[MeasureType, CliQuestionBuilder] = {
    MeasureType.LIGHT: _light,
    MeasureType.SPEAKER: _speaker,
    MeasureType.RECORDER: _recorder,
    MeasureType.AVERAGE: _average,
    MeasureType.CHARGING: _charging,
    MeasureType.FAN: _fan,
}


def measurement_questions(
    measure_type: MeasureType,
    environment: CliEnvironment,
    entity_catalog: HomeAssistantEntityCatalog | None = None,
) -> list[Question]:
    try:
        questions = CLI_QUESTION_BUILDERS[measure_type](environment, entity_catalog)
    except KeyError as error:
        raise ValueError(f"No CLI question builder registered for {measure_type}") from error
    if environment.selected_power_meter == PowerMeterType.HASS:
        questions.extend(hass_power_meter_questions(_require_entity_catalog(entity_catalog)))
    return questions
