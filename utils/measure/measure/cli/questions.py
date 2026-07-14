from __future__ import annotations

import re
from typing import Any

import inquirer  # type: ignore[import-untyped]
from inquirer.questions import Question  # type: ignore[import-untyped]

from measure.const import QUESTION_DUMMY_LOAD, QUESTION_ENTITY_ID, QUESTION_GENERATE_MODEL_JSON
from measure.controller.charging.const import (
    ATTR_BATTERY_LEVEL,
    QUESTION_BATTERY_LEVEL_ATTRIBUTE,
    QUESTION_BATTERY_LEVEL_ENTITY,
    QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
    BatteryLevelSourceType,
    ChargingDeviceType,
)
from measure.controller.light.const import LutMode
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


def average_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_DURATION,
            message="For how long do you want to measure? In seconds",
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
            validate=lambda _, current: re.match(r"\d+", current),
        ),
    ]


def hass_charging_controller_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_ENTITY_ID,
            message="Enter the charging device entity ID",
            validate=_not_empty,
        ),
        inquirer.List(
            name=QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
            message="How is the battery level exposed?",
            choices=[
                ("As an attribute of the main entity", BatteryLevelSourceType.ATTRIBUTE),
                ("As a separate entity", BatteryLevelSourceType.ENTITY),
            ],
        ),
        inquirer.Text(
            name=QUESTION_BATTERY_LEVEL_ATTRIBUTE,
            message="Enter the battery level attribute",
            default=ATTR_BATTERY_LEVEL,
            ignore=lambda answers: answers.get(QUESTION_BATTERY_LEVEL_SOURCE_TYPE) == BatteryLevelSourceType.ENTITY,
        ),
        inquirer.Text(
            name=QUESTION_BATTERY_LEVEL_ENTITY,
            message="Enter the battery level entity ID",
            ignore=lambda answers: answers.get(QUESTION_BATTERY_LEVEL_SOURCE_TYPE) == BatteryLevelSourceType.ATTRIBUTE,
            validate=_not_empty,
        ),
    ]


def hass_fan_controller_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_ENTITY_ID,
            message="Enter the fan entity ID",
            validate=_not_empty,
        ),
    ]


def hass_light_controller_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_ENTITY_ID,
            message="Enter the light entity ID",
            validate=_not_empty,
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


def hass_media_controller_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_ENTITY_ID,
            message="Enter the media player entity ID",
            validate=_not_empty,
        ),
    ]


def hass_power_meter_questions() -> list[Question]:
    return [
        inquirer.Text(
            name=QUESTION_POWERMETER_ENTITY_ID,
            message="Enter the power sensor entity ID",
            validate=_not_empty,
        ),
        inquirer.Text(
            name=QUESTION_VOLTAGEMETER_ENTITY_ID,
            message="Enter an optional voltage sensor entity ID",
            ignore=lambda answers: (
                not answers.get(QUESTION_DUMMY_LOAD, False) and not answers.get(QUESTION_GENERATE_MODEL_JSON, False)
            ),
        ),
    ]
