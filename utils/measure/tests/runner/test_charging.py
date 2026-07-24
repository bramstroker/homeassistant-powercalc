from unittest.mock import MagicMock, call

from measure.controller.charging.const import ATTR_BATTERY_LEVEL, ChargingDeviceType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.spec import DummyChargingControllerSpec
from measure.execution import RunInteraction
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import ChargingMeasurementRequest
from measure.runner.charging import ChargingRunner
from measure.tuning import MeasurementParameters
from measure.util.measure_util import MeasurementResult, MeasureUtil


def test_run_reports_battery_and_charging_operating_points() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.get_battery_level.side_effect = [99, 99, 100]
    controller.battery_level_attribute = ATTR_BATTERY_LEVEL
    controller.is_charging.return_value = True
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=10.5, voltages=[])
    measure_util.take_average_measurement.return_value = MeasurementResult(power=5.0, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = ChargingRunner(measure_util, MeasurementParameters(), controller, interaction)
    request = ChargingMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyChargingControllerSpec(),
        charging_device_type=ChargingDeviceType.VACUUM_ROBOT,
    )

    runner.run(request, "")

    interaction.phase.assert_any_call("Starting charging measurement")
    assert interaction.progress.call_args_list[0] == call(99, 100, phase="Charging")
    # The trickle phase must keep reporting progress with a countdown.
    trickle_progress = measure_util.take_average_measurement.call_args.kwargs["on_progress"]
    trickle_progress(60.0, 1800.0)
    assert interaction.progress.call_args_list[-1] == call(60, 1800, phase="Trickle charging", remaining_seconds=1740.0)
    assert [call.args[0] for call in interaction.operating_point.call_args_list] == [
        {"type": "charging", "battery_level": 99, "charging": True},
        {"type": "charging", "battery_level": 99, "charging": True},
        {"type": "charging", "battery_level": 100, "charging": True},
    ]


def test_fast_test_mode_skips_charging_waits_and_trickle_average() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.get_battery_level.side_effect = [99, 100]
    controller.battery_level_attribute = ATTR_BATTERY_LEVEL
    controller.is_charging.return_value = True
    measure_util = MagicMock(spec=MeasureUtil)
    measure_util.take_measurement.return_value = MeasurementResult(power=10.5, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = ChargingRunner(measure_util, MeasurementParameters(fast_test_mode=True), controller, interaction)
    request = ChargingMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyChargingControllerSpec(),
        charging_device_type=ChargingDeviceType.VACUUM_ROBOT,
        fast_test_mode=True,
    )

    runner.run(request, "")

    assert measure_util.take_measurement.call_count == 2
    measure_util.take_average_measurement.assert_not_called()
    interaction.wait.assert_not_called()


def test_generated_profile_uses_discovered_battery_sensor_state() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.battery_level_attribute = None
    runner = ChargingRunner(MagicMock(spec=MeasureUtil), MeasurementParameters(), controller)
    runner.charging_device_type = ChargingDeviceType.VACUUM_ROBOT

    model_data = runner._build_model_json_data({50: [10.0]})  # noqa: SLF001

    assert model_data["linear_config"] == {"calibrate": ["50 -> 10.0"]}


def test_generated_profile_keeps_battery_level_attribute_fallback() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.battery_level_attribute = ATTR_BATTERY_LEVEL
    runner = ChargingRunner(MagicMock(spec=MeasureUtil), MeasurementParameters(), controller)
    runner.charging_device_type = ChargingDeviceType.VACUUM_ROBOT

    model_data = runner._build_model_json_data({50: [10.0]})  # noqa: SLF001

    assert model_data["linear_config"] == {
        "attribute": ATTR_BATTERY_LEVEL,
        "calibrate": ["50 -> 10.0"],
    }
