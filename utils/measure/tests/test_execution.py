from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from measure.execution import MeasurementExecution, PreparedMeasurement
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import AverageMeasurementRequest
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasurementResult
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


def test_execution_writes_model_from_prepared_measurement(tmp_path: Path) -> None:
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
        runner.cleanup.assert_called_once_with()
        return MeasurementResult(power=0.5, voltages=[230.4])

    runner.measure_standby_power.side_effect = measure_standby_power
    prepared = PreparedMeasurement(
        request=request,
        runner=runner,
    )

    MeasurementExecution(measurement=prepared, output_directory=tmp_path).run()

    model = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    assert model["name"] == "Test device"
    assert model["measure_device"] == "Test meter"
    assert model["standby_power"] == 0.5
    assert model["device_type"] == "generic"
    assert model["min_voltage"] == 229.9
    assert model["max_voltage"] == 231.2
    assert model["measure_settings"]["SAMPLE_COUNT"] == 3


def test_execution_cleans_up_runner_after_failure(tmp_path: Path) -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec(), duration=1)
    runner = MagicMock(spec=MeasurementRunner)
    runner.run.side_effect = RuntimeError("measurement failed")
    runner.writes_export_files.return_value = False
    prepared = PreparedMeasurement(
        request=request,
        runner=runner,
    )

    with pytest.raises(RuntimeError, match="measurement failed"):
        MeasurementExecution(measurement=prepared, output_directory=tmp_path / "unused").run()

    runner.cleanup.assert_called_once_with()
