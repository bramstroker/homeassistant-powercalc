from __future__ import annotations

import re
from typing import Any

import inquirer
from inquirer.questions import Question

from measure.const import QUESTION_DUMMY_LOAD, QUESTION_ENTITY_ID, QUESTION_GENERATE_MODEL_JSON
from measure.controller.charging.const import (
    ATTR_BATTERY_LEVEL,
    QUESTION_BATTERY_LEVEL_ATTRIBUTE,
    QUESTION_BATTERY_LEVEL_ENTITY,
    QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
    BatteryLevelSourceType,
    ChargingDeviceType,
)
from measure.controller.charging.spec import charging_entity_domain
from measure.controller.light.const import LutMode
from measure.home_assistant_entities import (
    DeviceClass,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID, QUESTION_VOLTAGEMETER_ENTITY_ID
from measure.runner.const import (
    DEFAULT_EXPORT_FILENAME,
    QUESTION_CHARGING_DEVICE_TYPE,
    QUESTION_DISABLE_STREAMING,
    QUESTION_DURATION,
    QUESTION_EXPORT_FILENAME,
    QUESTION_GZIP,
    QUESTION_MODE,
    QUESTION_MULTIPLE_LIGHTS,
    QUESTION_NUM_LIGHTS,
)


def _not_empty(_: Any, current: str) -> bool:  # noqa: ANN401
    return bool(current.strip())


def _positive_number(_: Any, current: str) -> bool:  # noqa: ANN401
    return re.fullmatch(r"\d+", current) is not None and int(current) > 0


def _entity_choices(entities: list[EntityDescriptor]) -> list[tuple[str, str]]:
    return [(f"{entity.name} · {entity.entity_id}", entity.entity_id) for entity in entities]


def average_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_DURATION,
            message="For how long do you want to measure? In seconds",
            validate=_positive_number,
        ),
    ]


def recorder_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_EXPORT_FILENAME,
            message="To which file do you want to export?",
            default=DEFAULT_EXPORT_FILENAME,
        ),
    ]


def charging_questions() -> list[Question]:
    return [
        inquirer.List(
            name=QUESTION_CHARGING_DEVICE_TYPE,
            message="Select the charging device type",
            choices=[(charging_device_type.value, charging_device_type) for charging_device_type in ChargingDeviceType],
        ),
    ]


def speaker_questions() -> list[Question]:
    return [
        inquirer.Confirm(
            name=QUESTION_DISABLE_STREAMING,
            message="Amazon Alexa devices do not support direct streaming. Set this option to `y` to disable automatic streaming. You need to manually stream pink noise. See the documentation for more info",  # noqa: E501
            default=False,
        ),
    ]


def light_questions(*, supports_effects: bool) -> list[Question]:
    modes: list[tuple[LutMode | str, set[LutMode]]] = [
        (LutMode.HS, {LutMode.HS}),
        (LutMode.COLOR_TEMP, {LutMode.COLOR_TEMP}),
        (LutMode.BRIGHTNESS, {LutMode.BRIGHTNESS}),
        ("hs + color_temp", {LutMode.HS, LutMode.COLOR_TEMP}),
    ]
    if supports_effects:
        modes.append((LutMode.EFFECT, {LutMode.EFFECT}))
        modes.append(("hs + color_temp + effect", {LutMode.HS, LutMode.COLOR_TEMP, LutMode.EFFECT}))

    return [
        inquirer.List(
            name=QUESTION_MODE,
            message="Select the mode",
            choices=modes,
            default=LutMode.HS,
        ),
        inquirer.Confirm(
            name=QUESTION_GZIP,
            message="Do you want to gzip CSV files?",
            default=True,
        ),
        inquirer.Confirm(
            name=QUESTION_MULTIPLE_LIGHTS,
            message=(
                "Are you measuring multiple lights. In some situations it helps to connect multiple lights to "
                "be able to measure low currents."
            ),
            default=False,
        ),
        inquirer.Text(
            name=QUESTION_NUM_LIGHTS,
            message="How many lights are you measuring?",
            ignore=lambda answers: not answers.get(QUESTION_MULTIPLE_LIGHTS),
            validate=_positive_number,
        ),
    ]


def hass_charging_controller_questions(entity_catalog: HomeAssistantEntityCatalog) -> list[Question]:
    def entity_choices(answers: dict[str, Any]) -> list[tuple[str, str]]:
        device_type = ChargingDeviceType(answers[QUESTION_CHARGING_DEVICE_TYPE])
        domain = EntityDomain(charging_entity_domain(device_type))
        return _entity_choices(entity_catalog.load_snapshot().select(domain=domain))

    def attribute_choices(answers: dict[str, Any]) -> list[str]:
        entity_id = answers.get(QUESTION_ENTITY_ID)
        return entity_catalog.load_snapshot().attribute_names(str(entity_id)) if entity_id else []

    return [
        inquirer.List(
            name=QUESTION_ENTITY_ID,
            message="Select the charging device entity",
            choices=entity_choices,
        ),
        inquirer.List(
            name=QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
            message="How is the battery level exposed?",
            choices=[
                ("As an attribute of the main entity", BatteryLevelSourceType.ATTRIBUTE),
                ("As a separate entity", BatteryLevelSourceType.ENTITY),
            ],
        ),
        inquirer.List(
            name=QUESTION_BATTERY_LEVEL_ATTRIBUTE,
            message="Select the battery level attribute",
            choices=attribute_choices,
            default=ATTR_BATTERY_LEVEL,
            ignore=lambda answers: (
                answers.get(QUESTION_BATTERY_LEVEL_SOURCE_TYPE) == BatteryLevelSourceType.ENTITY
                or ATTR_BATTERY_LEVEL in attribute_choices(answers)
            ),
        ),
        inquirer.List(
            name=QUESTION_BATTERY_LEVEL_ENTITY,
            message="Select the battery level entity",
            choices=lambda _: _entity_choices(
                entity_catalog.load_snapshot().select(domain=EntityDomain.SENSOR),
            ),
            ignore=lambda answers: answers.get(QUESTION_BATTERY_LEVEL_SOURCE_TYPE) == BatteryLevelSourceType.ATTRIBUTE,
        ),
    ]


def hass_fan_controller_questions(entity_catalog: HomeAssistantEntityCatalog) -> list[Question]:
    return [
        inquirer.List(
            name=QUESTION_ENTITY_ID,
            message="Select the fan entity",
            choices=lambda _: _entity_choices(
                entity_catalog.load_snapshot().select(domain=EntityDomain.FAN),
            ),
        ),
    ]


def hass_light_controller_questions(entity_catalog: HomeAssistantEntityCatalog) -> list[Question]:
    return [
        inquirer.List(
            name=QUESTION_ENTITY_ID,
            message="Select the light entity",
            choices=lambda _: _entity_choices(
                entity_catalog.load_snapshot().select(domain=EntityDomain.LIGHT),
            ),
        ),
    ]


def hue_light_controller_questions() -> list[Question]:
    def get_message(answers: dict[str, Any]) -> str:
        target = "group" if answers.get(QUESTION_MULTIPLE_LIGHTS) else "light"
        return f"Enter the Hue {target} as {target}:<id>"

    return [
        inquirer.Text(
            name="light",
            message=get_message,
            validate=lambda _, current: re.fullmatch(r"(?:light|group):\d+", current) is not None,
        ),
    ]


def hass_media_controller_questions(entity_catalog: HomeAssistantEntityCatalog) -> list[Question]:
    return [
        inquirer.List(
            name=QUESTION_ENTITY_ID,
            message="Select the media player",
            choices=lambda _: _entity_choices(
                entity_catalog.load_snapshot().select(domain=EntityDomain.MEDIA_PLAYER),
            ),
        ),
    ]


def hass_power_meter_questions(entity_catalog: HomeAssistantEntityCatalog) -> list[Question]:
    related_voltage: dict[str, str | None] = {}

    def default_voltage(answers: dict[str, Any]) -> str | None:
        power_entity = str(answers.get(QUESTION_POWERMETER_ENTITY_ID, ""))
        if not power_entity:
            return None
        if power_entity not in related_voltage:
            related_voltage[power_entity] = entity_catalog.load_snapshot().related_entity_id(
                power_entity,
                DeviceClass.VOLTAGE,
            )
        return related_voltage[power_entity]

    def ignore_voltage(answers: dict[str, Any]) -> bool:
        if not answers.get(QUESTION_DUMMY_LOAD, False) and not answers.get(QUESTION_GENERATE_MODEL_JSON, False):
            return True
        return default_voltage(answers) is not None or not entity_catalog.load_snapshot().select(
            device_class=DeviceClass.VOLTAGE,
        )

    return [
        inquirer.List(
            name=QUESTION_POWERMETER_ENTITY_ID,
            message="Select the power sensor",
            choices=lambda _: _entity_choices(
                entity_catalog.load_snapshot().select(device_class=DeviceClass.POWER),
            ),
        ),
        inquirer.List(
            name=QUESTION_VOLTAGEMETER_ENTITY_ID,
            message="Select the voltage sensor",
            choices=lambda _: _entity_choices(
                entity_catalog.load_snapshot().select(device_class=DeviceClass.VOLTAGE),
            ),
            default=default_voltage,
            ignore=ignore_voltage,
        ),
    ]
