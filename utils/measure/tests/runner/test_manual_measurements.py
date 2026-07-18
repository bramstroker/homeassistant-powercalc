from pathlib import Path
from unittest.mock import MagicMock

from measure.execution import MeasurementCancelledError, RunInteraction
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import AverageMeasurementRequest, RecorderMeasurementRequest
from measure.runner.average import AverageRunner
from measure.runner.recorder import RecorderRunner
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


def test_recorder_reports_start_phase_after_confirmation(tmp_path: Path) -> None:
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    interaction.wait.side_effect = MeasurementCancelledError
    runner = RecorderRunner(measure_util, interaction)

    with pytest.raises(MeasurementCancelledError):
        runner.run(RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec()), str(tmp_path))

    interaction.confirm.assert_called_once_with("Ready to start recording. Stop the measurement when you are finished.")
    interaction.phase.assert_called_once_with("Starting recording")


def test_recorder_treats_cli_interrupt_as_successful_stop(tmp_path: Path) -> None:
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=4.2, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    interaction.wait.side_effect = KeyboardInterrupt
    runner = RecorderRunner(measure_util, interaction)

    result = runner.run(RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec()), str(tmp_path))

    assert result.summary is not None
    assert result.summary["Samples recorded"] == "1"
