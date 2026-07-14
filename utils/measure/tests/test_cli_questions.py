from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import inquirer
from measure.cli.main import Measure
from measure.cli.measurements import CLI_QUESTION_BUILDERS, measurement_questions
from measure.const import QUESTION_DUMMY_LOAD, QUESTION_ENTITY_ID, QUESTION_MODEL_ID, MeasureType
from measure.controller.charging.const import (
    QUESTION_BATTERY_LEVEL_ATTRIBUTE,
    QUESTION_BATTERY_LEVEL_ENTITY,
    QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
    BatteryLevelSourceType,
    ChargingControllerType,
    ChargingDeviceType,
)
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.media.const import MediaControllerType
from measure.home_assistant import HomeAssistantManager
from measure.home_assistant_entities import (
    DeviceClass,
    EntityCatalogSnapshot,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID, QUESTION_VOLTAGEMETER_ENTITY_ID, PowerMeterType
from measure.runner.const import (
    QUESTION_CHARGING_DEVICE_TYPE,
    QUESTION_DISABLE_STREAMING,
    QUESTION_DURATION,
    QUESTION_EXPORT_FILENAME,
    QUESTION_GZIP,
    QUESTION_MODE,
    QUESTION_MULTIPLE_LIGHTS,
    QUESTION_NUM_LIGHTS,
)
import pytest

from tests.conftest import MockConfigFactory


def _entity(
    entity_id: str,
    domain: EntityDomain,
    *,
    name: str | None = None,
    device_class: DeviceClass | None = None,
    device_id: str | None = None,
    model_id: str | None = None,
    state: str = "on",
    unit: str | None = None,
    attributes: list[str] | None = None,
) -> EntityDescriptor:
    return EntityDescriptor(
        entity_id=entity_id,
        name=name or entity_id,
        domain=domain,
        device_class=device_class,
        device_id=device_id,
        model_id=model_id,
        state=state,
        unit=unit,
        attribute_names=attributes or [],
        supported_modes=[] if domain == EntityDomain.LIGHT else None,
    )


def _catalog(*entities: EntityDescriptor) -> HomeAssistantEntityCatalog:
    catalog = MagicMock(spec=HomeAssistantEntityCatalog)
    catalog.load_snapshot.return_value = EntityCatalogSnapshot(list(entities))
    return cast(HomeAssistantEntityCatalog, catalog)


def test_every_measure_type_has_an_explicit_cli_builder() -> None:
    assert set(CLI_QUESTION_BUILDERS) == set(MeasureType)


@pytest.mark.parametrize(
    ("measure_type", "expected_names"),
    [
        (
            MeasureType.LIGHT,
            [QUESTION_MODE, QUESTION_GZIP, QUESTION_MULTIPLE_LIGHTS, QUESTION_NUM_LIGHTS],
        ),
        (MeasureType.SPEAKER, [QUESTION_DISABLE_STREAMING]),
        (MeasureType.RECORDER, [QUESTION_EXPORT_FILENAME]),
        (MeasureType.AVERAGE, [QUESTION_DURATION]),
        (MeasureType.CHARGING, [QUESTION_CHARGING_DEVICE_TYPE]),
        (MeasureType.FAN, []),
    ],
)
def test_cli_measurement_question_names_are_stable(
    mock_config_factory: MockConfigFactory,
    measure_type: MeasureType,
    expected_names: list[str],
) -> None:
    questions = measurement_questions(measure_type, mock_config_factory())

    assert isinstance(questions, list)
    assert [question.name for question in questions] == expected_names


def test_hass_adapter_fields_are_collected_as_entity_selectors(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory(
        {
            "selected_light_controller": LightControllerType.HASS,
            "selected_power_meter": PowerMeterType.HASS,
        },
    )

    entity_catalog = _catalog(
        _entity("light.desk", EntityDomain.LIGHT).model_copy(update={"supported_modes": [LutMode.BRIGHTNESS]}),
        _entity(
            "sensor.desk_power",
            EntityDomain.SENSOR,
            device_class=DeviceClass.POWER,
            state="1.2",
            unit="W",
        ),
        _entity(
            "sensor.desk_voltage",
            EntityDomain.SENSOR,
            device_class=DeviceClass.VOLTAGE,
            state="230",
            unit="V",
        ),
    )
    questions = measurement_questions(MeasureType.LIGHT, environment, entity_catalog)

    assert [question.name for question in questions] == [
        QUESTION_MODE,
        QUESTION_GZIP,
        QUESTION_MULTIPLE_LIGHTS,
        QUESTION_NUM_LIGHTS,
        QUESTION_ENTITY_ID,
        QUESTION_POWERMETER_ENTITY_ID,
        QUESTION_VOLTAGEMETER_ENTITY_ID,
    ]
    entity_question = next(question for question in questions if question.name == QUESTION_ENTITY_ID)
    power_question = next(question for question in questions if question.name == QUESTION_POWERMETER_ENTITY_ID)
    assert isinstance(entity_question, inquirer.List)
    assert entity_question.choices == ["light.desk"]
    assert isinstance(power_question, inquirer.List)
    assert power_question.choices == ["sensor.desk_power"]


def test_hass_voltage_selector_prefills_the_sensor_from_the_same_device(
    mock_config_factory: MockConfigFactory,
) -> None:
    environment = mock_config_factory({"selected_power_meter": PowerMeterType.HASS})
    entity_catalog = _catalog(
        _entity(
            "sensor.desk_power",
            EntityDomain.SENSOR,
            device_class=DeviceClass.POWER,
            device_id="desk-plug",
            state="1.2",
            unit="W",
        ),
        _entity(
            "sensor.desk_voltage",
            EntityDomain.SENSOR,
            device_class=DeviceClass.VOLTAGE,
            device_id="desk-plug",
            state="230",
            unit="V",
        ),
    )

    voltage_question = next(
        question
        for question in measurement_questions(MeasureType.AVERAGE, environment, entity_catalog)
        if question.name == QUESTION_VOLTAGEMETER_ENTITY_ID
    )
    voltage_question.answers = {
        QUESTION_POWERMETER_ENTITY_ID: "sensor.desk_power",
        QUESTION_DUMMY_LOAD: True,
    }

    assert voltage_question.default == "sensor.desk_voltage"
    assert voltage_question.ignore is True


@pytest.mark.parametrize(
    ("measure_type", "controller_setting", "controller_type", "domain", "entity_id"),
    [
        (
            MeasureType.SPEAKER,
            "selected_media_controller",
            MediaControllerType.HASS,
            "media_player",
            "media_player.office",
        ),
        (MeasureType.FAN, "selected_fan_controller", FanControllerType.HASS, "fan", "fan.office"),
    ],
)
def test_hass_controller_questions_list_domain_entities(
    mock_config_factory: MockConfigFactory,
    measure_type: MeasureType,
    controller_setting: str,
    controller_type: object,
    domain: str,
    entity_id: str,
) -> None:
    environment = mock_config_factory({controller_setting: controller_type})
    entity_catalog = _catalog(_entity(entity_id, EntityDomain(domain)))

    question = next(
        question
        for question in measurement_questions(measure_type, environment, entity_catalog)
        if question.name == QUESTION_ENTITY_ID
    )

    assert isinstance(question, inquirer.List)
    assert question.choices == [entity_id]


def test_hass_charging_questions_use_selected_device_and_battery_entities(
    mock_config_factory: MockConfigFactory,
) -> None:
    environment = mock_config_factory({"selected_charging_controller": ChargingControllerType.HASS})
    entity_catalog = _catalog(
        _entity(
            "vacuum.downstairs",
            EntityDomain.VACUUM,
            attributes=["battery_level", "status"],
        ),
        _entity("sensor.vacuum_battery", EntityDomain.SENSOR, state="80"),
    )
    questions = measurement_questions(MeasureType.CHARGING, environment, entity_catalog)

    entity_question = next(question for question in questions if question.name == QUESTION_ENTITY_ID)
    entity_question.answers = {QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT}
    assert entity_question.choices == ["vacuum.downstairs"]

    attribute_question = next(question for question in questions if question.name == QUESTION_BATTERY_LEVEL_ATTRIBUTE)
    attribute_question.answers = {
        QUESTION_ENTITY_ID: "vacuum.downstairs",
        QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ATTRIBUTE,
    }
    assert attribute_question.choices == ["battery_level", "status"]
    assert attribute_question.ignore is True

    battery_entity_question = next(question for question in questions if question.name == QUESTION_BATTERY_LEVEL_ENTITY)
    battery_entity_question.answers = {QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ENTITY}
    assert battery_entity_question.choices == ["sensor.vacuum_battery"]


def test_hue_target_is_entered_directly(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory({"selected_light_controller": LightControllerType.HUE})

    questions = measurement_questions(MeasureType.LIGHT, environment)

    assert questions[-1].name == "light"


def test_hass_entity_precedes_model_id_and_prefills_from_device(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory(
        {
            "selected_light_controller": LightControllerType.HASS,
            "selected_power_meter": PowerMeterType.DUMMY,
            "hass_url": "ws://homeassistant.local:8123/api/websocket",
            "hass_token": "token",
        },
    )
    measure = Measure(environment)

    entity_catalog = _catalog(
        _entity(
            "light.desk",
            EntityDomain.LIGHT,
            model_id="LWA017",
        ).model_copy(update={"supported_modes": [LutMode.BRIGHTNESS]}),
    )
    measure._entity_catalog = entity_catalog  # noqa: SLF001
    with patch("measure.cli.main.HomeAssistantManager"):
        questions = measure.get_questions(measurement_questions(MeasureType.LIGHT, environment, entity_catalog))
        names = [question.name for question in questions]
        model_question = questions[names.index(QUESTION_MODEL_ID)]
        model_question.answers = {QUESTION_ENTITY_ID: "light.desk"}

        assert names.index(QUESTION_ENTITY_ID) < names.index(QUESTION_MODEL_ID)
        assert model_question.default == "LWA017"


def test_cli_reuses_and_closes_prefill_manager(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory(
        {
            "selected_light_controller": LightControllerType.HASS,
            "selected_power_meter": PowerMeterType.DUMMY,
        },
    )
    measure = Measure(environment)
    home_assistant = MagicMock(spec=HomeAssistantManager)
    measure._home_assistant = home_assistant  # noqa: SLF001

    with (
        patch.object(measure, "_select_measure_type"),
        patch.object(measure, "_log_selected_controllers"),
        patch("measure.cli.main.measurement_questions", return_value=[]),
        patch.object(measure, "ask_questions", return_value={}),
        patch("measure.cli.main.request_from_answers"),
        patch("measure.cli.main.MeasurementAssembler") as assembler,
    ):
        assembler.return_value.assemble.side_effect = RuntimeError("stop after assembly")
        with pytest.raises(RuntimeError, match="stop after assembly"):
            measure.start()

    assert assembler.call_args.kwargs["home_assistant"] is home_assistant
    home_assistant.close.assert_called_once_with()
