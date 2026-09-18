from typing import cast
from unittest.mock import MagicMock, patch

import inquirer
from measure.cli.const import (
    QUESTION_CHARGING_DEVICE_TYPE,
    QUESTION_DISABLE_STREAMING,
    QUESTION_DUMMY_LOAD,
    QUESTION_DURATION,
    QUESTION_ENTITY_ID,
    QUESTION_GZIP,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODE,
    QUESTION_MODEL_ID,
    QUESTION_MODEL_NAME,
    QUESTION_MULTIPLE_LIGHTS,
    QUESTION_NUM_LIGHTS,
    QUESTION_POWERMETER_ENTITY_ID,
    QUESTION_VOLTAGEMETER_ENTITY_ID,
)
from measure.cli.main import Measure
from measure.cli.measurements import CLI_QUESTION_BUILDERS, measurement_questions
from measure.cli.questions import average_questions, hue_light_controller_questions
from measure.const import MeasureType
from measure.controller.charging.const import ChargingControllerType, ChargingDeviceType
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import LightControllerType, LutMode
from measure.controller.media.const import MediaControllerType
from measure.home_assistant.client import HomeAssistantManager
from measure.home_assistant.entities import (
    DeviceClass,
    EntityCatalogSnapshot,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import PowerMeterType
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
    "measure_type, expected_names",
    [
        (
            MeasureType.LIGHT,
            [QUESTION_MODE, QUESTION_GZIP, QUESTION_MULTIPLE_LIGHTS, QUESTION_NUM_LIGHTS],
        ),
        (MeasureType.SPEAKER, [QUESTION_DISABLE_STREAMING]),
        (MeasureType.RECORDER, []),
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


@pytest.mark.parametrize("has_voltage_sensor", [False, True])
def test_hass_voltage_selector_handles_missing_related_sensor(
    mock_config_factory: MockConfigFactory,
    has_voltage_sensor: bool,
) -> None:
    environment = mock_config_factory({"selected_power_meter": PowerMeterType.HASS})
    entities = [_entity("sensor.power", EntityDomain.SENSOR, device_class=DeviceClass.POWER, state="1.2", unit="W")]
    if has_voltage_sensor:
        entities.append(
            _entity("sensor.voltage", EntityDomain.SENSOR, device_class=DeviceClass.VOLTAGE, state="230", unit="V")
        )
    catalog = _catalog(*entities)
    question = next(
        question
        for question in measurement_questions(MeasureType.AVERAGE, environment, catalog)
        if question.name == QUESTION_VOLTAGEMETER_ENTITY_ID
    )

    assert question.default is None
    question.answers = {QUESTION_POWERMETER_ENTITY_ID: "sensor.power", QUESTION_DUMMY_LOAD: True}
    assert question.default is None
    assert question.ignore is not has_voltage_sensor
    assert question.choices == (["sensor.voltage"] if has_voltage_sensor else [])


def test_average_voltage_prompt_is_skipped_without_voltage_dependent_options(
    mock_config_factory: MockConfigFactory,
) -> None:
    environment = mock_config_factory({"selected_power_meter": PowerMeterType.HASS})
    catalog = _catalog(
        _entity("sensor.power", EntityDomain.SENSOR, device_class=DeviceClass.POWER, state="1.2", unit="W"),
        _entity("sensor.voltage", EntityDomain.SENSOR, device_class=DeviceClass.VOLTAGE, state="230", unit="V"),
    )
    question = next(
        question
        for question in measurement_questions(MeasureType.AVERAGE, environment, catalog)
        if question.name == QUESTION_VOLTAGEMETER_ENTITY_ID
    )
    question.answers = {QUESTION_POWERMETER_ENTITY_ID: "sensor.power", QUESTION_DUMMY_LOAD: False}

    assert question.ignore is True
    catalog.load_snapshot.assert_not_called()


@pytest.mark.parametrize(
    "measure_type, controller_setting, controller_type, domain, entity_id",
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


def test_hass_charging_questions_use_selected_device(
    mock_config_factory: MockConfigFactory,
) -> None:
    environment = mock_config_factory({"selected_charging_controller": ChargingControllerType.HASS})
    entity_catalog = _catalog(
        _entity(
            "vacuum.downstairs",
            EntityDomain.VACUUM,
            attributes=["battery_level", "status"],
        ),
    )
    questions = measurement_questions(MeasureType.CHARGING, environment, entity_catalog)

    entity_question = next(question for question in questions if question.name == QUESTION_ENTITY_ID)
    entity_question.answers = {QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT}
    assert entity_question.choices == ["vacuum.downstairs"]


def test_hue_target_is_entered_directly(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory({"selected_light_controller": LightControllerType.HUE})

    questions = measurement_questions(MeasureType.LIGHT, environment)

    assert questions[-1].name == "light"


@pytest.mark.parametrize(
    "measure_type, setting, adapter",
    [
        (MeasureType.LIGHT, "selected_light_controller", LightControllerType.HASS),
        (MeasureType.SPEAKER, "selected_media_controller", MediaControllerType.HASS),
        (MeasureType.FAN, "selected_fan_controller", FanControllerType.HASS),
        (MeasureType.CHARGING, "selected_charging_controller", ChargingControllerType.HASS),
        (MeasureType.AVERAGE, "selected_power_meter", PowerMeterType.HASS),
    ],
)
def test_home_assistant_question_builders_require_entity_catalog(
    mock_config_factory: MockConfigFactory,
    measure_type: MeasureType,
    setting: str,
    adapter: object,
) -> None:
    environment = mock_config_factory({setting: adapter})

    with pytest.raises(ValueError, match="entity choices require an entity catalog"):
        measurement_questions(measure_type, environment)


@pytest.mark.parametrize("duration", ["0", "-1", "1.5", "invalid", ""])
def test_average_duration_question_rejects_non_positive_integers(duration: str) -> None:
    question = average_questions()[0]

    with pytest.raises(inquirer.errors.ValidationError):
        question.validate(duration)


def test_average_duration_question_accepts_positive_integer() -> None:
    assert average_questions()[0].validate("60") is None


@pytest.mark.parametrize("multiple, target", [(False, "light"), (True, "group")])
def test_hue_target_prompt_reflects_multiple_lights_selection(multiple: bool, target: str) -> None:
    question = hue_light_controller_questions()[0]
    question.answers = {QUESTION_MULTIPLE_LIGHTS: multiple}

    assert question.message == f"Enter the Hue {target} as {target}:<id>"
    assert question.validate(f"{target}:1") is None


def test_hass_entity_precedes_model_id_and_prefills_from_device(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory(
        {
            "selected_light_controller": LightControllerType.HASS,
            "selected_power_meter": PowerMeterType.DUMMY,
            "hass_url": "ws://127.0.0.1:8123/api/websocket",
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


@pytest.mark.parametrize("entity_id, lookup_fails", [("", False), ("light.missing", False), ("light.desk", True)])
def test_model_id_default_handles_missing_metadata_and_caches_failures(
    mock_config_factory: MockConfigFactory,
    entity_id: str,
    lookup_fails: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    environment = mock_config_factory({"selected_light_controller": LightControllerType.HASS})
    catalog = _catalog()
    if lookup_fails:
        catalog.load_snapshot.side_effect = OSError("HA unavailable")
    measure = Measure(environment)

    with (
        patch("measure.cli.main.HomeAssistantManager"),
        patch("measure.cli.main.HomeAssistantEntityCatalog", return_value=catalog),
    ):
        questions = measure.get_questions([])
        question = next(question for question in questions if question.name == QUESTION_MODEL_ID)
        question.answers = {QUESTION_ENTITY_ID: entity_id}

        assert question.default is None
        assert question.default is None

    assert catalog.load_snapshot.call_count == (1 if entity_id else 0)
    if lookup_fails:
        assert "Could not prefill model ID for light.desk: HA unavailable" in caplog.text


@pytest.mark.parametrize(
    "model_id, explicit_model, explicit_name, expected_model, expected_name",
    [
        ("LWA017", None, None, "LWA017", "Hue desk lamp"),
        ("Model (EU)+1", None, None, "Model (EU)+1", "Hue desk lamp"),
        ("../unsafe", None, None, "", "Hue desk lamp"),
        ("a" * 121, None, None, "", "Hue desk lamp"),
        (None, None, None, "", "Hue desk lamp"),
        ("LWA017", "manual-model", "Manual lamp", "manual-model", "Manual lamp"),
    ],
)
def test_cli_wizard_prefills_safe_metadata_without_overwriting_answers(
    mock_config_factory: MockConfigFactory,
    model_id: str | None,
    explicit_model: str | None,
    explicit_name: str | None,
    expected_model: str,
    expected_name: str,
) -> None:
    environment = mock_config_factory(
        {"selected_measure_type": MeasureType.LIGHT, "selected_light_controller": LightControllerType.HASS}
    )
    descriptor = _entity("light.desk", EntityDomain.LIGHT, model_id=model_id).model_copy(
        update={"product_name": "Hue desk lamp"}
    )
    catalog = _catalog(descriptor)
    answers = {
        QUESTION_ENTITY_ID: "light.desk",
        QUESTION_MODE: {LutMode.BRIGHTNESS},
        QUESTION_MODEL_ID: explicit_model,
        QUESTION_MODEL_NAME: explicit_name,
        QUESTION_MEASURE_DEVICE: "Test meter",
    }
    measure = Measure(environment)

    with (
        patch("measure.cli.main.HomeAssistantManager") as manager,
        patch("measure.cli.main.HomeAssistantEntityCatalog", return_value=catalog),
        patch("measure.cli.main.measurement_questions", return_value=[]),
        patch.object(measure, "ask_questions", return_value=answers),
        patch("measure.cli.main.MeasurementAssembler") as assembler,
        patch("measure.cli.main.MeasurementExecution") as execution,
    ):
        execution.return_value.output_directory = None
        measure.start()

    request = assembler.return_value.assemble.call_args.args[0]
    assert request.model_id == expected_model
    assert request.product_name == expected_name
    execution.return_value.run.assert_called_once_with()
    manager.return_value.close.assert_called_once_with()


@pytest.mark.parametrize("lookup_fails", [False, True])
def test_cli_wizard_continues_without_home_assistant_metadata(
    mock_config_factory: MockConfigFactory, lookup_fails: bool, caplog: pytest.LogCaptureFixture
) -> None:
    environment = mock_config_factory(
        {"selected_measure_type": MeasureType.LIGHT, "selected_light_controller": LightControllerType.HASS}
    )
    catalog = _catalog()
    if lookup_fails:
        catalog.load_snapshot.side_effect = OSError("HA unavailable")
    measure = Measure(environment)
    answers = {
        QUESTION_ENTITY_ID: "light.desk",
        QUESTION_MODE: {LutMode.BRIGHTNESS},
        QUESTION_MEASURE_DEVICE: "Test meter",
    }

    with (
        patch("measure.cli.main.HomeAssistantManager") as manager,
        patch("measure.cli.main.HomeAssistantEntityCatalog", return_value=catalog),
        patch("measure.cli.main.measurement_questions", return_value=[]),
        patch.object(measure, "ask_questions", return_value=answers),
        patch("measure.cli.main.MeasurementAssembler") as assembler,
        patch("measure.cli.main.MeasurementExecution") as execution,
    ):
        execution.return_value.output_directory = None
        measure.start()

    request = assembler.return_value.assemble.call_args.args[0]
    assert request.model_id == ""
    assert request.product_name == ""
    execution.return_value.run.assert_called_once_with()
    manager.return_value.close.assert_called_once_with()
    if lookup_fails:
        assert "Could not prefill device details for light.desk: HA unavailable" in caplog.text
