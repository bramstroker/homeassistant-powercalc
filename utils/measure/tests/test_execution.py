import json
from pathlib import Path
from unittest.mock import MagicMock

from jsonschema import validate
from measure.controller.light.spec import DummyLightControllerSpec
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
    LightMeasurementRequest,
    RecorderMeasurementRequest,
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
    monkeypatch.setattr("measure.version.PROJECT_DIR", str(tmp_path))
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
    assert model["voltage_range"]["min"] == pytest.approx(229.9)
    assert model["voltage_range"]["max"] == pytest.approx(231.2)
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

    execution = MeasurementExecution(measurement=prepared, output_directory=tmp_path)
    with pytest.raises(RuntimeError, match="standby failed"):
        execution.run()

    runner.cleanup.assert_called_once_with()


def test_execution_analyses_complex_recording_and_writes_schema_valid_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".VERSION").write_text("v0.1.0:test", encoding="utf-8")
    monkeypatch.setattr("measure.version.PROJECT_DIR", str(tmp_path))
    request = RecorderMeasurementRequest(
        product_name="Test switch",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.device",),
    )
    runner = MagicMock(spec=MeasurementRunner)
    runner.writes_export_files.return_value = True

    def write_recording(_: RecorderMeasurementRequest, export_directory: str) -> RunnerResult:
        records = [
            {
                "elapsed_seconds": index,
                "power": 0.2 if index % 2 == 0 else 5.2,
                "entities": {"switch.device": {"state": "off" if index % 2 == 0 else "on", "attributes": {}}},
            }
            for index in range(20)
        ]
        Path(export_directory, "record.jsonl").write_text(
            "".join(f"{json.dumps(record)}\n" for record in records),
            encoding="utf-8",
        )
        return RunnerResult(model_json_data={}, voltages=[229.5, 231.0], summary={"Samples recorded": "20"})

    runner.run.side_effect = write_recording
    interaction = MagicMock(spec=RunInteraction)
    prepared = PreparedMeasurement(request=request, runner=runner, interaction=interaction)

    result = MeasurementExecution(measurement=prepared, output_directory=tmp_path).run()

    analysis = json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8"))
    model = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    schema_path = Path(__file__).parents[3] / "profile_library" / "model_schema.json"
    validate(model, json.loads(schema_path.read_text(encoding="utf-8")))
    assert analysis["status"] == "model_ready"
    assert analysis["feature"] == "switch.device.state"
    assert model["device_type"] == "generic_iot"
    assert model["calculation_strategy"] == "fixed"
    assert model["fixed_config"]["states_power"] == {"off": 0.2, "on": 5.2}
    assert model["standby_power"] == pytest.approx(0.2)
    assert result.summary is not None
    assert result.summary["Recording analysis"] == "Fixed states_power profile created"
    interaction.phase.assert_called_once_with("Analysing recording")
    runner.measure_standby_power.assert_not_called()


def test_execution_preserves_recording_when_analysis_fails(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.device",),
    )
    runner = MagicMock(spec=MeasurementRunner)
    runner.writes_export_files.return_value = True

    def write_recording(_: RecorderMeasurementRequest, export_directory: str) -> RunnerResult:
        Path(export_directory, "record.jsonl").write_text("raw recording\n", encoding="utf-8")
        return RunnerResult(model_json_data={}, summary={"Samples recorded": "1"})

    runner.run.side_effect = write_recording
    analyser = MagicMock()
    analyser.analyse.side_effect = RuntimeError("broken analyser")
    prepared = PreparedMeasurement(request=request, runner=runner)

    result = MeasurementExecution(measurement=prepared, output_directory=tmp_path, analyser=analyser).run()

    assert (tmp_path / "record.jsonl").read_text(encoding="utf-8") == "raw recording\n"
    analysis = json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["status"] == "insufficient_data"
    assert "broken analyser" in analysis["reason"]
    assert not (tmp_path / "model.json").exists()
    assert result.summary == {
        "Samples recorded": "1",
        "Recording analysis": "Failed",
        "Recording analysis reason": "Recording analysis failed: broken analyser",
    }
    assert "Recording analysis failed: broken analyser" in caplog.text


def test_execution_completes_without_model_when_recording_is_insufficient(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.device",),
    )
    runner = MagicMock(spec=MeasurementRunner)
    runner.writes_export_files.return_value = True

    def write_recording(_: RecorderMeasurementRequest, export_directory: str) -> RunnerResult:
        records = [
            {
                "elapsed_seconds": index,
                "power": 3,
                "entities": {"switch.device": {"state": "on", "attributes": {}}},
            }
            for index in range(10)
        ]
        Path(export_directory, "record.jsonl").write_text(
            "invalid line\n" + "".join(f"{json.dumps(record)}\n" for record in records),
            encoding="utf-8",
        )
        return RunnerResult(model_json_data={}, summary={"Samples recorded": "10"})

    runner.run.side_effect = write_recording
    prepared = PreparedMeasurement(request=request, runner=runner)

    result = MeasurementExecution(measurement=prepared, output_directory=tmp_path).run()

    analysis = json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["status"] == "insufficient_data"
    assert analysis["warnings"] == [
        "Skipped 1 invalid recorder line(s); first was line 1: Expecting value: line 1 column 1 (char 0)",
    ]
    assert not (tmp_path / "model.json").exists()
    assert result.summary == {
        "Samples recorded": "10",
        "Recording analysis": "More data needed",
        "Recording analysis reason": (
            "No state or scalar attribute had 2-20 usable values with at least 4 training samples per value"
        ),
    }
    assert "Profile was not created" in caplog.text
    assert "Skipped 1 invalid recorder line(s)" in caplog.text


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
    assert interaction.confirm.call_args_list[0].kwargs == {}
    assert interaction.confirm.call_args_list[1].kwargs == {"action": "Start measurement"}
    assert "Connect the target device in parallel" in interaction.confirm.call_args_list[1].args[0]
    assert "calibration is complete" not in interaction.confirm.call_args_list[1].args[0]
    measure_util.set_dummy_load_resistance.assert_called_once_with(812.4)


def test_dummy_load_calibration_repeats_until_steady_and_saves_result(monkeypatch: pytest.MonkeyPatch) -> None:
    request = LightMeasurementRequest(
        model_id="test-light",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
    )
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
    first_confirmation, second_confirmation = interaction.confirm.call_args_list
    assert "Disconnect the light" in first_confirmation.args[0]
    assert "only the preheated resistive dummy load" in first_confirmation.args[0]
    assert first_confirmation.kwargs == {"action": "Start dummy-load calibration"}
    assert "Dummy-load calibration is complete" in second_confirmation.args[0]
    assert "Connect the light in parallel" in second_confirmation.args[0]
    assert second_confirmation.kwargs == {"action": "Start measurement"}


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
