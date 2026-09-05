from collections.abc import Callable
import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

from measure.execution import MeasurementCancelledError, RunInteraction
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import AverageMeasurementRequest, RecorderMeasurementRequest
from measure.runner.average import AverageRunner
from measure.runner.recorder import RecorderEntityState, RecorderRunner
from measure.util.measure_util import MeasurementResult, MeasureUtil
import pytest


def test_average_reports_start_phase_after_confirmation() -> None:
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_average_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = AverageRunner(measure_util, interaction)

    runner.run(AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=10), "")

    interaction.confirm.assert_called_once_with("Ready to start the average measurement.")
    interaction.phase.assert_called_once_with("Starting averaging")
    assert measure_util.take_average_measurement.call_args.kwargs["finish_on_interrupt"] is True


def test_average_summary_uses_elapsed_duration() -> None:
    measure_util = MagicMock(spec=MeasureUtil)

    def average(
        duration: int,
        *,
        on_progress: Callable[[float, float], None],
        finish_on_interrupt: bool,
    ) -> MeasurementResult:
        assert duration == 60
        assert finish_on_interrupt is True
        on_progress(6.5, duration)
        return MeasurementResult(power=4.2, voltages=[230.0, 232.0])

    measure_util.take_average_measurement.side_effect = average
    runner = AverageRunner(measure_util, MagicMock(spec=RunInteraction))
    result = runner.run(AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=60), "")
    assert result.summary == {"Average power": "4.2 W", "Duration": "6.5 s", "Average voltage": "231.0 V"}


def test_recorder_treats_app_stop_as_successful_completion(tmp_path: Path) -> None:
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    interaction.wait.side_effect = MeasurementCancelledError
    runner = RecorderRunner(measure_util, interaction)

    request = RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec())
    export_directory = str(tmp_path)
    result = runner.run(request, export_directory)

    interaction.confirm.assert_called_once_with("Ready to start recording. Stop the measurement when you are finished.")
    interaction.phase.assert_called_once_with("Starting recording")
    assert result.summary is not None
    assert result.summary["Samples recorded"] == "1"
    assert next(csv.reader((tmp_path / "record.csv").read_text().splitlines()))[1] == "4.2"


def test_recorder_treats_cli_interrupt_as_successful_stop(tmp_path: Path) -> None:
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    interaction.wait.side_effect = KeyboardInterrupt
    runner = RecorderRunner(measure_util, interaction)

    result = runner.run(RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec()), str(tmp_path))

    assert result.summary is not None
    assert result.summary["Samples recorded"] == "1"
    assert next(csv.reader((tmp_path / "record.csv").read_text().splitlines()))[1] == "4.2"


def test_recorder_writes_entity_states_as_json_lines(tmp_path: Path) -> None:
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    interaction.wait.side_effect = KeyboardInterrupt
    state_reader = MagicMock(
        return_value={
            "vacuum.robot": RecorderEntityState("cleaning", {"status": "Cleaning", "battery_level": 42}),
            "sensor.robot_battery": RecorderEntityState("42", {"unit_of_measurement": "%"}),
        },
    )
    runner = RecorderRunner(measure_util, interaction, state_reader)
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id="vacuum.robot",
        battery_entity_id="sensor.robot_battery",
    )

    runner.run(request, str(tmp_path))

    samples = [json.loads(line) for line in (tmp_path / "record.jsonl").read_text().splitlines()]
    assert len(samples) == 1
    assert samples[0]["power"] == 4.2
    assert samples[0]["entities"] == {
        "vacuum.robot": {
            "state": "cleaning",
            "attributes": {"battery_level": 42, "status": "Cleaning"},
        },
        "sensor.robot_battery": {
            "state": "42",
            "attributes": {"unit_of_measurement": "%"},
        },
    }
    interaction.entity_states.assert_called_once_with(
        {"vacuum.robot": "cleaning", "sensor.robot_battery": "42"},
    )


def test_recorder_skips_unreadable_samples_and_keeps_recording(tmp_path: Path) -> None:
    """A reloading integration costs one sample, not the whole recording."""

    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    interaction.wait.side_effect = [None, None, KeyboardInterrupt]
    state_reader = MagicMock(
        side_effect=[
            {"switch.plug": RecorderEntityState("on", {})},
            RuntimeError("state unavailable"),
            {"switch.plug": RecorderEntityState("off", {})},
        ],
    )
    runner = RecorderRunner(measure_util, interaction, state_reader)
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.plug",),
    )

    result = runner.run(request, str(tmp_path))

    samples = [json.loads(line) for line in (tmp_path / "record.jsonl").read_text().splitlines()]
    assert [sample["entities"]["switch.plug"]["state"] for sample in samples] == ["on", "off"]
    assert result.summary is not None
    assert result.summary["Samples recorded"] == "2"


def test_recorder_stops_when_cancelled_while_reading_states(tmp_path: Path) -> None:
    """Cancellation raised by the state read still ends the run, unlike a read failure."""

    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    state_reader = MagicMock(side_effect=MeasurementCancelledError("stopped"))
    runner = RecorderRunner(measure_util, interaction, state_reader)
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.plug",),
    )

    result = runner.run(request, str(tmp_path))

    assert result.summary is not None
    assert result.summary["Samples recorded"] == "0"


def test_recorder_requires_state_reader_for_complex_recording(tmp_path: Path) -> None:
    runner = RecorderRunner(MagicMock(spec=MeasureUtil), MagicMock(spec=RunInteraction))
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.plug",),
    )

    with pytest.raises(ValueError, match="state reader is required"):
        runner.run(request, str(tmp_path))
