import csv
from dataclasses import dataclass, replace
import itertools
import os.path
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from measure.cancellation import MeasurementCancelledError
from measure.cli.const import QUESTION_MODE
from measure.cli.questions import light_questions
from measure.controller.errors import ApiConnectionError as HassApiConnectionError
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import DummyLightControllerSpec
from measure.powermeter.errors import OutdatedMeasurementError, PowerMeterError, ZeroReadingError
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import LightMeasurementRequest
from measure.runner.errors import RunnerError
from measure.runner.interaction import RunInteraction
from measure.runner.light.csv import inspect_light_csv, repair_incomplete_csv_tail
from measure.runner.light.plan import (
    ColorTempVariation,
    EffectVariation,
    HsVariation,
    LightMeasurementPlan,
    LightModePlan,
    Variation,
    build_light_plan,
    estimate_light_time_left,
)
from measure.runner.light.runner import LightRunner, LightRunProgress, MeasurementRunInput
from measure.tuning import MeasurementParameters
from measure.utils.sampling import AverageMeasurementConvergence, MeasurementResult, PowerSampler
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


def _zero_sleep_parameters() -> MeasurementParameters:
    return replace(
        _parameters(),
        sleep_initial=0,
        sleep_time=0,
        sleep_time_ct=0,
        sleep_time_hue=0,
        sleep_time_sat=0,
        sleep_time_effect_change=0,
    )


@pytest.mark.parametrize(
    "previous,current,expected_waits",
    [
        (None, Variation(1), [2, 10]),
        (Variation(1), Variation(2), [2]),
        (ColorTempVariation(1, 250), ColorTempVariation(1, 200), [2, 13]),
        (ColorTempVariation(1, 200), ColorTempVariation(1, 250), [2]),
        (HsVariation(1, 100, 100), HsVariation(1, 50, 100), [2, 11]),
        (HsVariation(1, 100, 100), HsVariation(1, 100, 50), [2, 12]),
        (HsVariation(1, 100, 100), HsVariation(1, 50, 50), [2, 11, 12]),
        (HsVariation(1, 50, 50), HsVariation(1, 100, 100), [2]),
        (EffectVariation(1, "rainbow"), EffectVariation(2, "rainbow"), [2]),
        (EffectVariation(1, "rainbow"), EffectVariation(1, "fire"), [2, 14]),
    ],
)
def test_light_settling_waits_follow_dimension_changes(
    previous: Variation | None,
    current: Variation,
    expected_waits: list[float],
) -> None:
    interaction = MagicMock(spec=RunInteraction)
    parameters = MeasurementParameters(
        sleep_time=2,
        sleep_initial=10,
        sleep_time_hue=11,
        sleep_time_sat=12,
        sleep_time_ct=13,
        sleep_time_effect_change=14,
    )
    runner = LightRunner(MagicMock(spec=PowerSampler), parameters, DummyLightController(), interaction)

    runner.wait(current, previous)

    assert interaction.wait.call_args_list == [call(seconds) for seconds in expected_waits]


def test_zero_standby_reading_is_kept_as_zero() -> None:
    sampler = MagicMock(spec=PowerSampler)
    sampler.take_measurement.side_effect = ZeroReadingError("No consumption")
    controller = MagicMock(spec=LightController)
    interaction = MagicMock(spec=RunInteraction)
    runner = LightRunner(sampler, MeasurementParameters(sleep_standby=20), controller, interaction)

    assert runner.measure_standby_power() == MeasurementResult(power=0, voltages=[])
    controller.change_light_state.assert_called_once_with(LutMode.BRIGHTNESS, on=False)
    interaction.wait.assert_called_once_with(20)
    interaction.operating_point.assert_called_once_with({"type": "light", "on": False})


def test_outdated_standby_reading_is_remeasured_after_nudge() -> None:
    sampler = MagicMock(spec=PowerSampler)
    measurement = MeasurementResult(power=0.4, voltages=[230.0])
    sampler.take_measurement.side_effect = [OutdatedMeasurementError("Stale reading"), measurement]
    controller = MagicMock(spec=LightController)
    interaction = MagicMock(spec=RunInteraction)
    runner = LightRunner(sampler, MeasurementParameters(max_nudges=1), controller, interaction)

    assert runner.measure_standby_power() == measurement
    assert sampler.take_measurement.call_count == 2
    assert controller.change_light_state.call_args_list == [
        call(LutMode.BRIGHTNESS, on=False),
        call(LutMode.BRIGHTNESS, on=True, bri=255),
        call(LutMode.BRIGHTNESS, on=True, bri=0),
    ]


@pytest.mark.parametrize("seconds,expected", [(-1, "0s"), (30, "30s"), (90, "1.5m"), (5400, "1.5h")])
def test_time_left_is_formatted_for_display(seconds: float, expected: str) -> None:
    assert LightRunner.format_time_left(seconds) == expected


@pytest.mark.parametrize(
    "variation,expected_dimensions",
    [
        (ColorTempVariation(1, 250), {"color_temp_mired": 250}),
        (HsVariation(1, 100, 50), {"hue": 100, "saturation": 50}),
        (EffectVariation(1, "rainbow"), {"effect": "rainbow"}),
    ],
)
def test_light_run_reports_mode_specific_operating_point(
    tmp_path: Path,
    variation: Variation,
    expected_dimensions: dict[str, object],
) -> None:
    sampler = MagicMock(spec=PowerSampler)
    sampler.take_measurement.return_value = MeasurementResult(power=1, voltages=[])
    sampler.take_average_measurement.return_value = MeasurementResult(power=1, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = LightRunner(sampler, _zero_sleep_parameters(), DummyLightController(), interaction)
    runner.gzip = False
    runner.light_info = runner.light_controller.get_light_info()
    effects = [variation.effect] if isinstance(variation, EffectVariation) else []
    runner.active_plan = LightMeasurementPlan(modes=[LightModePlan(variation.mode, [variation])], effects=effects)
    run = MeasurementRunInput(variation.mode, str(tmp_path / "measurement.csv"), [variation], is_resuming=False)

    runner.run_mode(run, LightRunProgress(total=1, remaining=[variation]))

    interaction.operating_point.assert_called_with(
        {"type": "light", "on": True, "brightness": 1, **expected_dimensions}
    )


@dataclass
class _BrightnessRun:
    runner: LightRunner
    measurement_info: MeasurementRunInput
    progress: LightRunProgress
    sampler: MagicMock

    def execute(self) -> None:
        self.runner.run_mode(self.measurement_info, self.progress)


def _brightness_run(
    tmp_path: Path, variations: list[Variation], controller: LightController | None = None
) -> _BrightnessRun:
    measure_util_mock = MagicMock(PowerSampler)
    interaction = MagicMock(spec=RunInteraction)
    runner = LightRunner(measure_util_mock, _zero_sleep_parameters(), controller or DummyLightController(), interaction)
    runner.gzip = False
    runner.light_info = runner.light_controller.get_light_info()
    runner.active_plan = LightMeasurementPlan(
        modes=[LightModePlan(mode=LutMode.BRIGHTNESS, variations=variations)],
        effects=[],
    )
    progress = LightRunProgress(total=len(variations), remaining=variations.copy())
    measurement_info = MeasurementRunInput(
        mode=LutMode.BRIGHTNESS,
        csv_file=str(tmp_path / "brightness.csv"),
        variations=variations.copy(),
        is_resuming=False,
    )
    return _BrightnessRun(runner, measurement_info, progress, measure_util_mock)


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


@pytest.mark.parametrize(
    "property_name,value,expected",
    [
        ("min_mired", MIN_MIRED - 1, MIN_MIRED),
        ("min_mired", MIN_MIRED, MIN_MIRED),
        ("min_mired", 200, 200),
        ("max_mired", MAX_MIRED + 1, MAX_MIRED),
        ("max_mired", MAX_MIRED, MAX_MIRED),
        ("max_mired", 400, 400),
    ],
)
def test_light_info_limits_color_temperature_to_supported_bounds(property_name: str, value: int, expected: int) -> None:
    info = LightInfo("test-light")

    setattr(info, property_name, value)

    assert getattr(info, property_name) == expected


@pytest.mark.parametrize("effects", [None, []])
def test_effect_plan_requires_available_effects(effects: list[str] | None) -> None:
    with pytest.raises(RunnerError, match="No effects found for the light"):
        build_light_plan({LutMode.EFFECT}, _parameters(), LightInfo("test-light"), effects)


def test_empty_light_plan_has_no_remaining_measurement_time() -> None:
    plan = build_light_plan(set(), _parameters(), LightInfo("test-light"))

    assert plan.variation_count == 0
    assert estimate_light_time_left(plan, _parameters()) == 0


@pytest.mark.parametrize(
    "mode,expected_count",
    [
        (LutMode.BRIGHTNESS, 2),
        (LutMode.COLOR_TEMP, 4),
        (LutMode.HS, 8),
        (LutMode.EFFECT, 6),
    ],
)
def test_fast_test_mode_uses_only_dimension_endpoints(mode: LutMode, expected_count: int) -> None:
    controller = DummyLightController()
    plan = build_light_plan(
        {mode},
        replace(_parameters(), fast_test_mode=True),
        controller.get_light_info(),
        controller.get_effect_list(),
    )

    assert plan.variation_count == expected_count


def test_run(export_path: str) -> None:
    measure_util_mock = MagicMock(PowerSampler)
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


@pytest.mark.parametrize("completed_brightnesses", [[1], [1, 128]])
@pytest.mark.parametrize("incomplete_tail", ["", "255,", "255,\nbroken\n", "255,8.2"])
def test_resume_reports_progress_against_the_full_plan(
    tmp_path: Path,
    completed_brightnesses: list[int],
    incomplete_tail: str,
) -> None:
    parameters = replace(_zero_sleep_parameters(), bri_bri_steps=127)
    sampler = MagicMock(PowerSampler)
    sampler.take_measurement.return_value = MeasurementResult(power=1, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = LightRunner(
        sampler,
        parameters,
        DummyLightController(),
        interaction,
        resume=True,
    )
    request = LightMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
        modes={LutMode.BRIGHTNESS},
        parameters=parameters,
        gzip=False,
    )
    csv_path = tmp_path / "brightness.csv"
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["bri", "watt"])
        writer.writerows([brightness, 1.0] for brightness in completed_brightnesses)
        csv_file.write(incomplete_tail)

    runner.run(request, str(tmp_path))

    initial_progress = interaction.progress.call_args_list[0].kwargs
    assert initial_progress["completed"] == len(completed_brightnesses)
    assert initial_progress["total"] == 3
    final_progress = interaction.progress.call_args_list[-1].kwargs
    assert final_progress["completed"] == 3
    assert final_progress["total"] == 3
    with csv_path.open(newline="") as csv_file:
        rows = list(csv.reader(csv_file))
    assert [int(row[0]) for row in rows[1:]] == [1, 128, 255]
    assert [float(row[1]) for row in rows[1:]] == [1.0, 1.0, 1.0]


def test_initial_wait_happens_after_selecting_first_measurement_point(tmp_path: Path) -> None:
    events: list[tuple[str, object]] = []
    variation = Variation(1)
    light_controller = MagicMock(spec=DummyLightController)
    light_controller.change_light_state.side_effect = lambda *args, **kwargs: events.append(("change", (args, kwargs)))
    run = _brightness_run(tmp_path, [variation], light_controller)
    run.runner.config = replace(run.runner.config, sleep_time=2, sleep_initial=10)
    run.runner.interaction.wait.side_effect = lambda seconds: events.append(("wait", seconds))
    run.sampler.take_measurement.return_value = MeasurementResult(power=1, voltages=[])

    run.execute()

    assert events[:7] == [
        ("change", ((LutMode.BRIGHTNESS,), {"on": True, "bri": 255})),
        ("wait", 2),
        ("change", ((LutMode.BRIGHTNESS,), {"on": True, "bri": 255})),
        ("wait", 2),
        ("change", ((LutMode.BRIGHTNESS,), {"on": True, "bri": 1})),
        ("wait", 2),
        ("wait", 10),
    ]
    run.runner.interaction.phase.assert_called_once_with("Stabilizing light before the first reading (10 s)")


def test_zero_reading_retries_current_variation_and_reports_skipped_progress(tmp_path: Path) -> None:
    variations = [Variation(1), Variation(2)]
    run = _brightness_run(tmp_path, variations)
    run.sampler.take_measurement.side_effect = [
        ZeroReadingError("0 watt was read from the power meter"),
        MeasurementResult(power=1, voltages=[]),
        MeasurementResult(power=2, voltages=[]),
    ]

    run.execute()

    with open(run.measurement_info.csv_file, newline="") as csv_file:
        rows = list(csv.reader(csv_file))
    assert rows == [["bri", "watt"], ["1", "1.0"], ["2", "2.0"]]
    skipped_progress = run.runner.interaction.progress.call_args_list[1]
    assert skipped_progress.kwargs["completed"] == 0
    assert skipped_progress.kwargs["total"] == 2
    assert skipped_progress.kwargs["skipped"] == 1
    assert run.runner.interaction.progress.call_args_list[-1].kwargs["completed"] == 2
    assert run.runner.interaction.progress.call_args_list[-1].kwargs["total"] == 2


def test_zero_reading_counter_resets_after_valid_measurement(tmp_path: Path) -> None:
    variations = [Variation(1), Variation(2)]
    run = _brightness_run(tmp_path, variations)
    run.sampler.take_measurement.side_effect = [
        ZeroReadingError("first low reading"),
        MeasurementResult(power=1, voltages=[]),
        ZeroReadingError("second low reading"),
        ZeroReadingError("third low reading"),
        ZeroReadingError("fourth low reading"),
        ZeroReadingError("fifth low reading"),
        MeasurementResult(power=2, voltages=[]),
    ]

    run.execute()

    with open(run.measurement_info.csv_file, newline="") as csv_file:
        rows = list(csv.reader(csv_file))
        assert rows[-2:] == [["1", "1.0"], ["2", "2.0"]]


def test_zero_reading_retry_does_not_repeat_initial_stabilization(tmp_path: Path) -> None:
    run = _brightness_run(tmp_path, [Variation(1), Variation(2)])
    run.runner.config = replace(run.runner.config, sleep_initial=10)
    run.sampler.take_measurement.side_effect = [
        ZeroReadingError("zero"),
        MeasurementResult(power=1, voltages=[]),
        MeasurementResult(power=2, voltages=[]),
    ]

    run.execute()

    run.runner.interaction.phase.assert_called_once_with("Stabilizing light before the first reading (10 s)")
    assert run.runner.interaction.wait.call_args_list.count(call(10)) == 1
    assert run.progress.completed == 2


def test_meter_failure_keeps_variation_unfinished(tmp_path: Path) -> None:
    run = _brightness_run(tmp_path, [Variation(1)])
    error = PowerMeterError("Meter disconnected")
    run.sampler.take_measurement.side_effect = error

    with pytest.raises(RunnerError, match="Aborting measurement session: Meter disconnected") as raised:
        run.execute()

    assert raised.value.__cause__ is error
    assert run.progress.completed == 0
    assert Path(run.measurement_info.csv_file).read_text() == "bri,watt\n"


def test_cancellation_after_measurement_does_not_save_or_complete_variation(tmp_path: Path) -> None:
    run = _brightness_run(tmp_path, [Variation(1)])

    def finish_measurement(*_: object) -> MeasurementResult:
        run.runner.interaction.checkpoint.side_effect = MeasurementCancelledError()
        return MeasurementResult(power=1, voltages=[])

    run.sampler.take_measurement.side_effect = finish_measurement

    with pytest.raises(MeasurementCancelledError):
        run.execute()

    assert run.progress.completed == 0
    assert Path(run.measurement_info.csv_file).read_text() == "bri,watt\n"


def test_repeated_zero_readings_fail_fast_with_actionable_error(tmp_path: Path) -> None:
    variations = [Variation(1), Variation(2)]
    run = _brightness_run(tmp_path, variations)
    run.sampler.take_measurement.side_effect = ZeroReadingError("0 watt was read from the power meter")

    with pytest.raises(RunnerError) as error:
        run.execute()

    message = str(error.value)
    assert "repeated 0 W readings" in message
    assert "power meter may not resolve this low load" in message
    assert "multiple identical lights" in message
    assert "resistive dummy load" in message
    assert "https://docs.powercalc.nl/contributing/measure/troubleshooting/" in message
    assert run.sampler.take_measurement.call_count == 5
    assert run.runner.interaction.progress.call_args_list[-1].kwargs["skipped"] == 5


@pytest.mark.parametrize("brightness", [1, 200])
def test_nudge_restores_target_after_stale_and_zero_readings(tmp_path: Path, brightness: int) -> None:
    controller = MagicMock(spec=DummyLightController)
    run = _brightness_run(tmp_path, [Variation(brightness)], controller)
    runner = run.runner
    runner.config = replace(runner.config, max_nudges=3, pulse_time_nudge=2, sleep_time_nudge=10)
    run.sampler.take_measurement.side_effect = [
        OutdatedMeasurementError("stale"),
        ZeroReadingError("zero"),
        MeasurementResult(power=4.2, voltages=[230]),
    ]
    order = MagicMock()
    order.attach_mock(controller.change_light_state, "change")
    order.attach_mock(runner.interaction.wait, "wait")
    order.attach_mock(run.sampler.take_measurement, "measure")

    with patch("measure.runner.light.runner.time.time", return_value=1234):
        result = runner.nudge_and_remeasure(LutMode.BRIGHTNESS, Variation(brightness))

    assert result == MeasurementResult(power=4.2, voltages=[230])
    expected_attempt = [
        call.change(LutMode.BRIGHTNESS, on=brightness < 128, bri=255),
        call.wait(2),
        call.change(LutMode.BRIGHTNESS, on=True, bri=brightness),
        call.wait(10),
        call.measure(1234, 0),
    ]
    assert order.mock_calls == expected_attempt * 3
    assert runner.num_0_readings == 0
    assert runner.skipped_zero_readings == 1
    runner.interaction.operating_point.assert_called_with({"type": "light", "on": True, "brightness": brightness})


@pytest.mark.parametrize("max_nudges", [0, 2])
def test_nudging_stops_at_configured_retry_limit(tmp_path: Path, max_nudges: int) -> None:
    controller = MagicMock(spec=DummyLightController)
    run = _brightness_run(tmp_path, [Variation(1)], controller)
    run.runner.config = replace(run.runner.config, max_nudges=max_nudges)
    run.sampler.take_measurement.side_effect = OutdatedMeasurementError("stale")

    message = "nudging is disabled" if max_nudges == 0 else "Aborting after 2 nudge attempts"
    with pytest.raises(OutdatedMeasurementError, match=message):
        run.runner.nudge_and_remeasure(LutMode.BRIGHTNESS, Variation(1))

    assert run.sampler.take_measurement.call_count == max_nudges
    assert controller.change_light_state.call_count == 2 * max_nudges


def test_repeated_zero_readings_abort_before_nudge_budget_is_exhausted(tmp_path: Path) -> None:
    run = _brightness_run(tmp_path, [Variation(1)])
    run.runner.config = replace(run.runner.config, max_nudges=10)
    run.sampler.take_measurement.side_effect = ZeroReadingError("zero")

    with pytest.raises(RunnerError, match="repeated 0 W readings"):
        run.runner.nudge_and_remeasure(LutMode.BRIGHTNESS, Variation(1))

    assert run.sampler.take_measurement.call_count == 5
    assert run.runner.skipped_zero_readings == 5


def test_nudging_remains_cancellable_between_pulse_and_measurement(tmp_path: Path) -> None:
    controller = MagicMock(spec=DummyLightController)
    run = _brightness_run(tmp_path, [Variation(1)], controller)
    run.runner.config = replace(run.runner.config, max_nudges=3)
    run.runner.interaction.checkpoint.side_effect = [None, MeasurementCancelledError()]

    with pytest.raises(MeasurementCancelledError):
        run.runner.nudge_and_remeasure(LutMode.BRIGHTNESS, Variation(1))

    controller.change_light_state.assert_called_once_with(LutMode.BRIGHTNESS, on=True, bri=255)
    run.sampler.take_measurement.assert_not_called()


def test_stale_reading_is_replaced_by_recovered_measurement_in_csv(tmp_path: Path) -> None:
    run = _brightness_run(tmp_path, [Variation(1)])
    run.runner.config = replace(run.runner.config, max_nudges=1)
    run.sampler.take_measurement.side_effect = [
        OutdatedMeasurementError("stale"),
        MeasurementResult(power=4.2, voltages=[230]),
    ]

    run.execute()

    with Path(run.measurement_info.csv_file).open(newline="") as csv_file:
        assert list(csv.reader(csv_file)) == [["bri", "watt"], ["1", "4.2"]]
    assert run.sampler.take_measurement.call_count == 2
    assert run.progress.remaining == []


def test_resume_drops_incomplete_rows_without_losing_complete_measurements(tmp_path: Path) -> None:
    path = tmp_path / "brightness.csv"
    path.write_text("bri,watt\n1,1.25\n128,2.5\n255,\nbroken\n", encoding="utf-8")
    inspection = inspect_light_csv(path, LutMode.BRIGHTNESS)
    assert inspection.last_complete_variation == Variation(128)
    repair_incomplete_csv_tail(path, inspection)
    assert path.read_text() == "bri,watt\n1,1.25\n128,2.5\n"


def test_resume_with_only_incomplete_rows_has_no_completed_variation(tmp_path: Path) -> None:
    path = tmp_path / "brightness.csv"
    path.write_text("bri,watt\n1,\n", encoding="utf-8")
    inspection = inspect_light_csv(path, LutMode.BRIGHTNESS)
    assert inspection.last_complete_variation is None
    repair_incomplete_csv_tail(path, inspection)
    assert path.read_text() == "bri,watt\n"


@pytest.mark.parametrize(
    "contents,message",
    [
        ("wrong,watt\n1,1.0\n255,", "header does not match"),
        ("bri,watt\n999,1.0\n255,", "does not match the configured measurement grid"),
    ],
)
def test_resume_rejects_incompatible_csv_without_repairing_it(tmp_path: Path, contents: str, message: str) -> None:
    path = tmp_path / "brightness.csv"
    path.write_text(contents)
    runner = LightRunner(MagicMock(PowerSampler), _zero_sleep_parameters(), DummyLightController(), resume=True)
    request = LightMeasurementRequest(
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
        parameters=runner.config,
    )

    with pytest.raises(RunnerError, match=message):
        runner.run(request, str(tmp_path))

    assert path.read_text() == contents


def test_cleanup_turns_off_light() -> None:
    light_controller = MagicMock(spec=DummyLightController)
    runner = LightRunner(MagicMock(PowerSampler), _parameters(), light_controller)

    runner.cleanup()

    light_controller.change_light_state.assert_called_once_with(LutMode.BRIGHTNESS, on=False)
    light_controller.close.assert_called_once_with()


def test_cleanup_failure_does_not_mask_measurement_result(caplog: pytest.LogCaptureFixture) -> None:
    light_controller = MagicMock(spec=DummyLightController)
    light_controller.change_light_state.side_effect = RuntimeError("unavailable")
    runner = LightRunner(MagicMock(PowerSampler), _parameters(), light_controller)

    runner.cleanup()

    assert "Could not turn off the light during measurement cleanup: unavailable" in caplog.text
    light_controller.close.assert_called_once_with()


def test_controller_close_failure_does_not_mask_measurement_result(caplog: pytest.LogCaptureFixture) -> None:
    light_controller = MagicMock(spec=DummyLightController)
    light_controller.close.side_effect = RuntimeError("close unavailable")
    runner = LightRunner(MagicMock(PowerSampler), _parameters(), light_controller)

    runner.cleanup()

    assert "Could not close the light controller during measurement cleanup: close unavailable" in caplog.text


def _flaky_light_controller(failures_after_startup: int, *, start_failing_at: int = 2) -> MagicMock:
    """A light controller that drops its connection after ``start_failing_at`` calls.

    The first two calls belong to set_light_to_maximum_brightness, which runs before
    any variation is measured; ``start_failing_at=0`` targets that initial turn-on.
    """

    light_controller = MagicMock(spec=DummyLightController)
    calls = itertools.count()

    def change_light_state(*_: object, **__: object) -> None:
        index = next(calls)
        if index >= start_failing_at and index - start_failing_at < failures_after_startup:
            raise HassApiConnectionError("Failed to change light state: Connection broken")

    light_controller.change_light_state.side_effect = change_light_state
    return light_controller


def test_change_light_state_is_retried_after_a_dropped_connection(tmp_path: Path) -> None:
    """A Home Assistant light must survive a dropped WebSocket mid-session.

    HassLightController raises measure.controller.errors.ApiConnectionError, while the
    runner used to catch a same-named class from measure.controller.light.errors. The
    two were unrelated, so the retry never fired and hours-long sessions died on a
    single broken pipe. See issue #4543.
    """

    variations = [Variation(1), Variation(2)]
    run = _brightness_run(tmp_path, variations, _flaky_light_controller(failures_after_startup=1))
    run.sampler.take_measurement.side_effect = [
        MeasurementResult(power=1, voltages=[]),
        MeasurementResult(power=2, voltages=[]),
    ]

    run.execute()

    with open(run.measurement_info.csv_file, newline="") as csv_file:
        rows = list(csv.reader(csv_file))
    assert rows == [["bri", "watt"], ["1", "1.0"], ["2", "2.0"]]


def test_change_light_state_gives_up_after_five_failed_retries(tmp_path: Path) -> None:
    variations = [Variation(1)]
    run = _brightness_run(tmp_path, variations, _flaky_light_controller(failures_after_startup=5))

    with pytest.raises(RunnerError, match="Failed to change light state after 5 retries"):
        run.execute()


def test_initial_maximum_brightness_is_retried_after_a_dropped_connection(tmp_path: Path) -> None:
    """A dropped connection during the initial turn-on must not abort the session.

    The retry only covered the per-variation loop, so a single broken frame during
    set_light_to_maximum_brightness still killed the run before any measurement was
    written.
    """

    variations = [Variation(1), Variation(2)]
    run = _brightness_run(tmp_path, variations, _flaky_light_controller(failures_after_startup=1, start_failing_at=0))
    run.sampler.take_measurement.side_effect = [
        MeasurementResult(power=1, voltages=[]),
        MeasurementResult(power=2, voltages=[]),
    ]

    run.execute()

    with open(run.measurement_info.csv_file, newline="") as csv_file:
        rows = list(csv.reader(csv_file))
    assert rows == [["bri", "watt"], ["1", "1.0"], ["2", "2.0"]]


def test_initial_maximum_brightness_gives_up_after_five_failed_retries(tmp_path: Path) -> None:
    controller = _flaky_light_controller(failures_after_startup=5, start_failing_at=0)
    run = _brightness_run(tmp_path, [Variation(1)], controller)

    with pytest.raises(RunnerError, match="Failed to change light state after 5 retries"):
        run.execute()


def test_resume_effect(tmp_path: Path) -> None:
    """Test resume point is detected correctly for effect mode."""
    csv_file = tmp_path / "effect.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["effect", "bri", "watt"])
        writer.writerow(["colorloop", 100, 2.5])
        writer.writerow(["nightlight", 200, 3.0])

    resume_variation = inspect_light_csv(csv_file, LutMode.EFFECT).last_complete_variation
    assert isinstance(resume_variation, EffectVariation)
    assert resume_variation.effect == "nightlight"
    assert resume_variation.bri == 200


def test_resume_confirmation_uses_interaction(tmp_path: Path) -> None:
    csv_file = tmp_path / "brightness.csv"
    csv_file.write_text("bri,watt\n1,1.0\n")
    interaction = MagicMock(spec=RunInteraction)
    interaction.choose.return_value = False
    runner = LightRunner(
        MagicMock(PowerSampler),
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
    measure_util_mock = MagicMock(PowerSampler)
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
    measure_util_mock = MagicMock(PowerSampler)
    runner = LightRunner(measure_util_mock, _parameters(), DummyLightController())

    questions = light_questions(supports_effects=runner.light_controller.has_effect_support())
    mode_question = next(q for q in questions if q.name == QUESTION_MODE)
    choices = mode_question.choices

    assert ("hs + color_temp + effect", {LutMode.HS, LutMode.COLOR_TEMP, LutMode.EFFECT}) in choices
