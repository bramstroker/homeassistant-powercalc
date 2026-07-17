from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from measure.dummy_load import DummyLoadCalibration
from measure.execution import (
    DummyLoadPreparation,
    MeasurementCancelledError,
    MeasurementExecution,
    PreparedMeasurement,
    RunInteraction,
)
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import (
    AverageMeasurementRequest,
    DummyLoadCalibrationRequest,
    DummyLoadReuseRequest,
)
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasurementResult, MeasureUtil
import pytest


def test_execution_consumes_prepared_measurement_without_reassembling_fields(tmp_path: Path) -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=1)
    runner = MagicMock(spec=MeasurementRunner)
    runner.run.return_value = RunnerResult(model_json_data={})
    runner.writes_export_files.return_value = False
    prepared = PreparedMeasurement(
        request=request,
        runner=runner,
    )

    unused_output_directory = tmp_path / "unused"
    result = MeasurementExecution(
        measurement=prepared,
        output_directory=unused_output_directory,
    ).run()

    runner.run.assert_called_once_with(request, "")
    runner.cleanup.assert_called_once_with()
    assert not unused_output_directory.exists()
    assert result.model_json_data == {}


@pytest.mark.parametrize("measure_version", ["v0.1.0:app", "v0.1.0:cli"])
def test_execution_writes_model_from_prepared_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    measure_version: str,
) -> None:
    (tmp_path / ".VERSION").write_text(measure_version, encoding="utf-8")
    monkeypatch.setattr("measure.model.PROJECT_DIR", str(tmp_path))
    request = AverageMeasurementRequest(
        product_name="Test device",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        generate_model=True,
        parameters={"sample_count": 3},
    )
    runner = MagicMock(spec=MeasurementRunner)
    runner.run.return_value = RunnerResult(
        model_json_data={"device_type": "generic"},
        voltages=[231.2, 229.9],
    )

    def measure_standby_power() -> MeasurementResult:
        runner.cleanup.assert_not_called()
        return MeasurementResult(power=0.5, voltages=[230.4])

    runner.measure_standby_power.side_effect = measure_standby_power
    prepared = PreparedMeasurement(
        request=request,
        runner=runner,
    )

    MeasurementExecution(measurement=prepared, output_directory=tmp_path).run()

    runner.cleanup.assert_called_once_with()

    model = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    assert model["name"] == "Test device"
    assert model["measure_device"] == "Test meter"
    assert model["standby_power"] == pytest.approx(0.5)
    assert model["device_type"] == "generic"
    assert model["min_voltage"] == pytest.approx(229.9)
    assert model["max_voltage"] == pytest.approx(231.2)
    assert model["measure_settings"]["SAMPLE_COUNT"] == 3
    assert model["measure_settings"]["VERSION"] == measure_version


def test_execution_cleans_up_runner_after_failure(tmp_path: Path) -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=1)
    runner = MagicMock(spec=MeasurementRunner)
    runner.run.side_effect = RuntimeError("measurement failed")
    runner.writes_export_files.return_value = False
    prepared = PreparedMeasurement(
        request=request,
        runner=runner,
    )

    execution = MeasurementExecution(measurement=prepared, output_directory=tmp_path / "unused")

    with pytest.raises(RuntimeError, match="measurement failed"):
        execution.run()

    runner.cleanup.assert_called_once_with()


def test_execution_cleans_up_runner_after_standby_failure(tmp_path: Path) -> None:
    request = AverageMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        generate_model=True,
    )
    runner = MagicMock(spec=MeasurementRunner)
    runner.run.return_value = RunnerResult(model_json_data={})
    runner.measure_standby_power.side_effect = RuntimeError("standby failed")
    prepared = PreparedMeasurement(request=request, runner=runner)

    with pytest.raises(RuntimeError, match="standby failed"):
        MeasurementExecution(measurement=prepared, output_directory=tmp_path).run()

    runner.cleanup.assert_called_once_with()


def test_execution_runs_preparations_before_runner(tmp_path: Path) -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    calls: list[str] = []
    preparation = MagicMock()
    preparation.run.side_effect = lambda interaction: calls.append("prepare")
    runner = MagicMock(spec=MeasurementRunner)
    runner.writes_export_files.return_value = False
    runner.run.side_effect = lambda request, output: calls.append("run") or RunnerResult(model_json_data={})
    interaction = MagicMock(spec=RunInteraction)
    prepared = PreparedMeasurement(request=request, runner=runner, preparations=[preparation], interaction=interaction)

    MeasurementExecution(measurement=prepared, output_directory=tmp_path).run()

    assert calls == ["prepare", "run"]
    preparation.run.assert_called_once_with(interaction)


def test_dummy_load_reuse_requires_two_confirmations_and_configures_measure_util() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    measure_util = MagicMock(spec=MeasureUtil)
    interaction = MagicMock(spec=RunInteraction)
    preparation = DummyLoadPreparation(
        request=request,
        spec=DummyLoadReuseRequest(description="60 W lamp", resistance=812.4),
        measure_util=measure_util,
    )

    preparation.run(interaction)

    assert interaction.confirm.call_count == 2
    measure_util.set_dummy_load_resistance.assert_called_once_with(812.4)


def test_dummy_load_calibration_repeats_until_steady_and_saves_result(monkeypatch: pytest.MonkeyPatch) -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    measure_util = MagicMock(spec=MeasureUtil)
    interaction = MagicMock(spec=RunInteraction)
    calibration_store = MagicMock()
    calibration_store.load.return_value = None
    measure_util.take_average_measurement.side_effect = [
        *[MeasurementResult(power=float(index), voltages=[230.0]) for index in range(20)],
        *[MeasurementResult(power=100.0, voltages=[230.0]) for _ in range(20)],
    ]
    measure_util.dummy_load_trend.side_effect = ["increasing", "steady"]
    preparation = DummyLoadPreparation(
        request=request,
        spec=DummyLoadCalibrationRequest(description="60 W lamp"),
        measure_util=measure_util,
        calibration_store=calibration_store,
    )

    preparation.run(interaction)

    assert measure_util.take_average_measurement.call_count == 40
    measure_util.set_dummy_load_resistance.assert_called_once_with(100.0)
    calibration_store.save.assert_called_once_with(request, 100.0)
    assert interaction.confirm.call_count == 2


def test_dummy_load_cancelled_during_calibration_is_not_saved() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    measure_util = MagicMock(spec=MeasureUtil)
    interaction = MagicMock(spec=RunInteraction)
    interaction.checkpoint.side_effect = MeasurementCancelledError
    calibration_store = MagicMock()
    calibration_store.load.return_value = None
    preparation = DummyLoadPreparation(
        request=request,
        spec=DummyLoadCalibrationRequest(description="60 W lamp"),
        measure_util=measure_util,
        calibration_store=calibration_store,
    )

    with pytest.raises(MeasurementCancelledError):
        preparation.run(interaction)

    measure_util.take_average_measurement.assert_not_called()
    calibration_store.save.assert_not_called()
    measure_util.set_dummy_load_resistance.assert_not_called()


def test_dummy_load_calibration_uses_resumed_value() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    measure_util = MagicMock(spec=MeasureUtil)
    interaction = MagicMock(spec=RunInteraction)
    calibration_store = MagicMock()
    calibration_store.load.return_value = DummyLoadCalibration(
        description="60 W lamp",
        resistance=456.7,
        calibrated_at="2026-07-16T10:00:00+00:00",
        power_meter_fingerprint="meter",
    )
    preparation = DummyLoadPreparation(
        request=request,
        spec=DummyLoadCalibrationRequest(description="60 W lamp"),
        measure_util=measure_util,
        calibration_store=calibration_store,
    )

    preparation.run(interaction)

    measure_util.take_average_measurement.assert_not_called()
    measure_util.set_dummy_load_resistance.assert_called_once_with(456.7)
    calibration_store.save.assert_not_called()
