from unittest.mock import MagicMock, call

from measure.controller.fan.controller import FanController
from measure.controller.fan.dummy import DummyFanController
from measure.controller.fan.spec import DummyFanControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import FanMeasurementRequest
from measure.runner.fan import FanRunner
from measure.runner.interaction import RunInteraction
from measure.tuning import MeasurementParameters
from measure.utils.sampling import MeasurementResult, PowerSampler
import pytest


@pytest.mark.parametrize("fast_test_mode", [False, True])
def test_standby_turns_off_fan_and_preserves_measurement(fast_test_mode: bool) -> None:
    sampler = MagicMock(spec=PowerSampler)
    measurement = MeasurementResult(power=0.4, voltages=[231.2])
    sampler.take_measurement.return_value = measurement
    sampler.take_average_measurement.return_value = measurement
    controller = MagicMock(spec=FanController)
    interaction = MagicMock(spec=RunInteraction)
    runner = FanRunner(sampler, MeasurementParameters(fast_test_mode=fast_test_mode), controller, interaction)

    result = runner.measure_standby_power()

    assert result == measurement
    controller.turn_off.assert_called_once_with()
    interaction.operating_point.assert_called_once_with({"type": "fan", "percentage": 0, "on": False})
    if fast_test_mode:
        sampler.take_measurement.assert_called_once()
        sampler.take_average_measurement.assert_not_called()
        interaction.wait.assert_not_called()
    else:
        interaction.wait.assert_called_once_with(15)
        sampler.take_average_measurement.assert_called_once_with(20)
        sampler.take_measurement.assert_not_called()


def test_run(export_path: str) -> None:
    measure_util_mock = MagicMock(PowerSampler)
    measure_util_mock.take_average_measurement.return_value = MeasurementResult(power=10.50, voltages=[])
    runner = FanRunner(measure_util_mock, MeasurementParameters(), DummyFanController())
    request = FanMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyFanControllerSpec(),
    )
    result = runner.run(request, export_path)

    model_data = result.model_json_data
    assert model_data == {
        "device_type": "fan",
        "calculation_strategy": "linear",
        "linear_config": {
            "calibrate": [
                "5 -> 10.50",
                "10 -> 10.50",
                "15 -> 10.50",
                "20 -> 10.50",
                "25 -> 10.50",
                "30 -> 10.50",
                "35 -> 10.50",
                "40 -> 10.50",
                "45 -> 10.50",
                "50 -> 10.50",
                "55 -> 10.50",
                "60 -> 10.50",
                "65 -> 10.50",
                "70 -> 10.50",
                "75 -> 10.50",
                "80 -> 10.50",
                "85 -> 10.50",
                "90 -> 10.50",
                "95 -> 10.50",
                "100 -> 10.50",
            ],
        },
    }
    assert model_data["device_type"] == "fan"
    assert model_data["calculation_strategy"] == "linear"
    assert "linear_config" in model_data


def test_run_reports_fan_percentage_operating_points(export_path: str) -> None:
    sampler = MagicMock(PowerSampler)
    sampler.take_average_measurement.return_value = MeasurementResult(power=10.5, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = FanRunner(sampler, MeasurementParameters(), DummyFanController(), interaction)
    request = FanMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyFanControllerSpec(),
    )

    runner.run(request, export_path)

    interaction.phase.assert_any_call("Stabilizing fan at 5%")
    interaction.phase.assert_any_call("Measuring fan at 5%")
    # Progress must be reported before the first fan speed so the UI leaves the preparing state.
    # 20 steps of stabilize+measure (15+20 s).
    assert interaction.progress.call_args_list[0] == call(0, 20, phase="Measuring fan speeds", remaining_seconds=700)
    assert interaction.progress.call_args_list[-1] == call(20, 20, phase="Measuring fan speeds", remaining_seconds=0)
    points = [call.args[0] for call in interaction.operating_point.call_args_list]
    assert points[0] == {"type": "fan", "percentage": 5, "on": True}
    assert points[-1] == {"type": "fan", "percentage": 100, "on": True}


def test_fast_test_mode_measures_only_fan_endpoints_without_waiting(export_path: str) -> None:
    sampler = MagicMock(PowerSampler)
    sampler.take_measurement.return_value = MeasurementResult(power=10.5, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = FanRunner(sampler, MeasurementParameters(fast_test_mode=True), DummyFanController(), interaction)
    request = FanMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyFanControllerSpec(),
        fast_test_mode=True,
    )

    result = runner.run(request, export_path)

    assert result.model_json_data["linear_config"] == {"calibrate": ["5 -> 10.50", "100 -> 10.50"]}
    assert sampler.take_measurement.call_count == 2
    sampler.take_average_measurement.assert_not_called()
    interaction.wait.assert_not_called()
    assert interaction.progress.call_args_list[-1] == call(2, 2, phase="Measuring fan speeds", remaining_seconds=0)


def test_cleanup_turns_off_fan() -> None:
    fan_controller = MagicMock(FanController)
    runner = FanRunner(MagicMock(PowerSampler), MeasurementParameters(), fan_controller)

    runner.cleanup()

    fan_controller.turn_off.assert_called_once_with()


def test_cleanup_does_not_surface_fan_shutdown_failure() -> None:
    fan_controller = MagicMock(FanController)
    fan_controller.turn_off.side_effect = RuntimeError("offline")
    runner = FanRunner(MagicMock(PowerSampler), MeasurementParameters(), fan_controller)

    runner.cleanup()
