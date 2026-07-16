import csv
from dataclasses import replace
import os.path
from pathlib import Path
from unittest.mock import MagicMock

from measure.cli.questions import light_questions
from measure.controller.light.const import LutMode
from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import DummyLightControllerSpec
from measure.execution import RunInteraction
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import LightMeasurementRequest
from measure.runner.const import QUESTION_MODE
from measure.runner.light import EffectVariation, LightRunner
from measure.runner.light_plan import build_light_plan
from measure.tuning import MeasurementParameters
from measure.util.measure_util import AverageMeasurementConvergence, MeasurementResult, MeasureUtil
import pytest


def _parameters() -> MeasurementParameters:
    return MeasurementParameters(
        ct_bri_steps=5,
        ct_mired_steps=10,
        bri_bri_steps=1,
        hs_bri_steps=32,
        hs_hue_steps=2731,
        hs_sat_steps=32,
    )


@pytest.mark.parametrize(
    "mode,expected_count",
    [
        (
            LutMode.BRIGHTNESS,
            255,
        ),
        (
            LutMode.COLOR_TEMP,
            1872,
        ),
        (
            LutMode.HS,
            2025,
        ),
        (
            LutMode.EFFECT,
            24,
        ),
    ],
)
def test_get_variations(mode: LutMode, expected_count: int) -> None:
    controller = DummyLightController()
    plan = build_light_plan(
        {mode},
        _parameters(),
        controller.get_light_info(),
        controller.get_effect_list(),
    )

    assert plan.variation_count == expected_count


def test_run(export_path: str) -> None:
    measure_util_mock = MagicMock(MeasureUtil)
    measure_util_mock.take_measurement.return_value = MeasurementResult(power=1, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = LightRunner(measure_util_mock, _parameters(), DummyLightController(), interaction)
    request = LightMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
        modes={LutMode.BRIGHTNESS},
    )
    result = runner.run(request, export_path)
    assert result.model_json_data == {
        "device_type": "light",
        "calculation_strategy": "lut",
    }

    assert os.path.exists(os.path.join(export_path, "brightness.csv.gz"))
    remaining = [call.kwargs["remaining_seconds"] for call in interaction.progress.call_args_list]
    assert remaining[0] > remaining[-1]
    assert remaining[-1] == 0
    interaction.phase.assert_any_call("Stabilizing light before the first reading (10 s)")
    points = [call.args[0] for call in interaction.operating_point.call_args_list]
    assert points[0] == {"type": "light", "on": True, "brightness": 1}
    assert points[-1] == {"type": "light", "on": True, "brightness": 255}


def test_cleanup_turns_off_light() -> None:
    light_controller = MagicMock(spec=DummyLightController)
    runner = LightRunner(MagicMock(MeasureUtil), _parameters(), light_controller)

    runner.cleanup()

    light_controller.change_light_state.assert_called_once_with(LutMode.BRIGHTNESS, on=False)
    light_controller.close.assert_called_once_with()


def test_cleanup_failure_does_not_mask_measurement_result(caplog: pytest.LogCaptureFixture) -> None:
    light_controller = MagicMock(spec=DummyLightController)
    light_controller.change_light_state.side_effect = RuntimeError("unavailable")
    runner = LightRunner(MagicMock(MeasureUtil), _parameters(), light_controller)

    runner.cleanup()

    assert "Could not turn off the light during measurement cleanup: unavailable" in caplog.text
    light_controller.close.assert_called_once_with()


def test_controller_close_failure_does_not_mask_measurement_result(caplog: pytest.LogCaptureFixture) -> None:
    light_controller = MagicMock(spec=DummyLightController)
    light_controller.close.side_effect = RuntimeError("close unavailable")
    runner = LightRunner(MagicMock(MeasureUtil), _parameters(), light_controller)

    runner.cleanup()

    assert "Could not close the light controller during measurement cleanup: close unavailable" in caplog.text


def test_resume_effect(tmp_path: Path) -> None:
    """Test resume point is detected correctly for effect mode."""
    csv_file = tmp_path / "effect.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["effect", "bri", "watt"])
        writer.writerow(["colorloop", 100, 2.5])
        writer.writerow(["nightlight", 200, 3.0])

    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, _parameters(), DummyLightController())

    resume_variation = runner.get_resume_variation(str(csv_file), LutMode.EFFECT)
    assert isinstance(resume_variation, EffectVariation)
    assert resume_variation.effect == "nightlight"
    assert resume_variation.bri == 200


def test_resume_confirmation_uses_interaction(tmp_path: Path) -> None:
    csv_file = tmp_path / "brightness.csv"
    csv_file.write_text("bri,watt\n1,1.0\n")
    interaction = MagicMock(spec=RunInteraction)
    interaction.choose.return_value = False
    runner = LightRunner(
        MagicMock(MeasureUtil),
        replace(_parameters(), prompt_resume=True),
        DummyLightController(),
        interaction=interaction,
        resume=True,
    )

    assert runner.should_resume(str(csv_file)) is False
    interaction.choose.assert_called_once_with(
        f"CSV File {csv_file} already exists. Do you want to resume measurements?",
        default=True,
    )


def test_effect_measurement_uses_convergence_settings() -> None:
    parameters = replace(
        _parameters(),
        measure_time_effect=180,
        measure_time_effect_min=20,
        measure_time_effect_convergence_window=15,
        measure_time_effect_convergence_abs=0.1,
        measure_time_effect_convergence_rel=0.01,
    )
    measure_util_mock = MagicMock(MeasureUtil)
    measure_util_mock.take_average_measurement.return_value = MeasurementResult(power=10, voltages=[])
    runner = LightRunner(measure_util_mock, parameters, DummyLightController())

    runner.take_power_measurement(LutMode.EFFECT, start_timestamp=0)

    measure_util_mock.take_average_measurement.assert_called_once_with(
        180,
        convergence=AverageMeasurementConvergence(
            min_duration=20,
            window_duration=15,
            absolute_threshold=0.1,
            relative_threshold=0.01,
        ),
    )


def test_get_questions() -> None:
    """Test get_questions contains the new triple mode choice when effects are supported."""
    measure_util_mock = MagicMock(MeasureUtil)
    runner = LightRunner(measure_util_mock, _parameters(), DummyLightController())

    questions = light_questions(supports_effects=runner.light_controller.has_effect_support())
    mode_question = next(q for q in questions if q.name == QUESTION_MODE)
    choices = mode_question.choices

    assert ("hs + color_temp + effect", {LutMode.HS, LutMode.COLOR_TEMP, LutMode.EFFECT}) in choices
