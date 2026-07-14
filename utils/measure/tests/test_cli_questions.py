from __future__ import annotations

from unittest.mock import MagicMock, patch

from measure.cli.main import Measure
from measure.cli.measurements import CLI_QUESTION_BUILDERS, measurement_questions
from measure.const import QUESTION_ENTITY_ID, QUESTION_MODEL_ID, MeasureType
from measure.controller.light.const import LightControllerType
from measure.home_assistant import HomeAssistantManager
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


def test_hass_adapter_fields_are_collected_without_live_discovery(mock_config_factory: MockConfigFactory) -> None:
    environment = mock_config_factory(
        {
            "selected_light_controller": LightControllerType.HASS,
            "selected_power_meter": PowerMeterType.HASS,
        },
    )

    questions = measurement_questions(MeasureType.LIGHT, environment)

    assert [question.name for question in questions] == [
        QUESTION_MODE,
        QUESTION_GZIP,
        QUESTION_MULTIPLE_LIGHTS,
        QUESTION_NUM_LIGHTS,
        QUESTION_ENTITY_ID,
        QUESTION_POWERMETER_ENTITY_ID,
        QUESTION_VOLTAGEMETER_ENTITY_ID,
    ]


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
    questions = measure.get_questions(measurement_questions(MeasureType.LIGHT, environment))
    names = [question.name for question in questions]
    model_question = questions[names.index(QUESTION_MODEL_ID)]
    model_question.answers = {QUESTION_ENTITY_ID: "light.desk"}

    with patch("measure.cli.main.HomeAssistantManager") as manager_class:
        manager_class.return_value.get_device_model.return_value = "LWA017"

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
        pytest.raises(RuntimeError, match="stop after assembly"),
    ):
        assembler.return_value.assemble.side_effect = RuntimeError("stop after assembly")
        measure.start()

    assert assembler.call_args.kwargs["home_assistant"] is home_assistant
    home_assistant.close.assert_called_once_with()
