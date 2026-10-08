from unittest.mock import MagicMock, call

from measure.controller.charging.const import ATTR_BATTERY_LEVEL, ChargingDeviceType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.errors import ChargingControllerError
from measure.controller.charging.spec import DummyChargingControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import ChargingMeasurementRequest
from measure.runner.charging import ChargingRunner
from measure.runner.errors import RunnerError
from measure.runner.interaction import RunInteraction
from measure.tuning import MeasurementParameters
from measure.utils.sampling import MeasurementResult, PowerSampler
import pytest


@pytest.fixture
def charging_runner() -> ChargingRunner:
    controller = MagicMock(spec=ChargingController)
    controller.get_battery_level.side_effect = [99, 99, 100]
    controller.battery_level_attribute = ATTR_BATTERY_LEVEL
    controller.is_charging.return_value = True
    sampler = MagicMock(spec=PowerSampler)
    sampler.take_measurement.return_value = MeasurementResult(power=10, voltages=[230])
    sampler.take_average_measurement.return_value = MeasurementResult(power=2, voltages=[231])
    return ChargingRunner(sampler, MeasurementParameters(), controller, MagicMock(spec=RunInteraction))


@pytest.fixture
def charging_request() -> ChargingMeasurementRequest:
    return ChargingMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyChargingControllerSpec(),
        charging_device_type=ChargingDeviceType.VACUUM_ROBOT,
    )


def test_waiting_for_docking_announces_once_and_then_measures(
    charging_runner: ChargingRunner,
    charging_request: ChargingMeasurementRequest,
) -> None:
    charging_runner.controller.is_charging.side_effect = [False, False, False, True, True, True]
    charging_runner.controller.is_valid_state.return_value = True

    result = charging_runner.run(charging_request, "")

    assert charging_runner.interaction.wait.call_args_list[:2] == [call(1), call(1)]
    assert charging_runner.interaction.phase.call_args_list.count(call("Waiting for the device to start charging")) == 1
    charging_runner.interaction.notify.assert_any_call("Charging device started charging, starting measurements")
    assert result.model_json_data["linear_config"]["calibrate"] == ["99 -> 10.0", "100 -> 2.0"]
    assert result.voltages == [230, 230, 231]


def test_invalid_state_while_waiting_aborts_before_sampling(
    charging_runner: ChargingRunner,
    charging_request: ChargingMeasurementRequest,
) -> None:
    charging_runner.controller.is_charging.return_value = False
    charging_runner.controller.is_valid_state.return_value = False

    with pytest.raises(RunnerError, match="not in a valid state"):
        charging_runner.run(charging_request, "")

    charging_runner.sampler.take_measurement.assert_not_called()
    charging_runner.sampler.take_average_measurement.assert_not_called()


def test_undocking_during_measurement_aborts_without_trickle_profile(
    charging_runner: ChargingRunner,
    charging_request: ChargingMeasurementRequest,
) -> None:
    charging_runner.controller.is_charging.side_effect = [True, True, False]

    with pytest.raises(RunnerError, match="not charging anymore"):
        charging_runner.run(charging_request, "")

    charging_runner.sampler.take_measurement.assert_not_called()
    charging_runner.sampler.take_average_measurement.assert_not_called()


def test_charging_recovers_from_errors_and_resets_retry_budget(
    charging_runner: ChargingRunner,
    charging_request: ChargingMeasurementRequest,
) -> None:
    failures = [ChargingControllerError("Unavailable")] * 10
    charging_runner.controller.get_battery_level.side_effect = [99, *failures, 99, *failures, 100]

    result = charging_runner.run(charging_request, "")

    assert result.model_json_data["linear_config"]["calibrate"] == ["99 -> 10.0", "100 -> 2.0"]
    assert charging_runner.interaction.wait.call_count == 22
    assert charging_runner.sampler.take_measurement.call_count == 2


def test_charging_aborts_after_consecutive_controller_failures(
    charging_runner: ChargingRunner,
    charging_request: ChargingMeasurementRequest,
) -> None:
    failure = ChargingControllerError("Unavailable")
    charging_runner.controller.get_battery_level.side_effect = [99, *([failure] * 11)]

    with pytest.raises(RunnerError, match="Too many errors") as raised:
        charging_runner.run(charging_request, "")

    assert raised.value.__cause__ is failure
    assert charging_runner.interaction.wait.call_count == 10
    charging_runner.sampler.take_average_measurement.assert_not_called()


def test_already_charged_device_only_measures_trickle(
    charging_runner: ChargingRunner,
    charging_request: ChargingMeasurementRequest,
) -> None:
    charging_runner.controller.get_battery_level.side_effect = [100]

    result = charging_runner.run(charging_request, "")

    assert result.model_json_data["linear_config"]["calibrate"] == ["100 -> 2.0"]
    assert result.voltages == [231]
    charging_runner.sampler.take_measurement.assert_not_called()
    charging_runner.interaction.wait.assert_not_called()
    assert charging_runner.measure_standby_power() == MeasurementResult(power=0, voltages=[])


def test_run_reports_battery_and_charging_operating_points() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.get_battery_level.side_effect = [99, 99, 100]
    controller.battery_level_attribute = ATTR_BATTERY_LEVEL
    controller.is_charging.return_value = True
    sampler = MagicMock(spec=PowerSampler)
    sampler.take_measurement.return_value = MeasurementResult(power=10.5, voltages=[])
    sampler.take_average_measurement.return_value = MeasurementResult(power=5.0, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = ChargingRunner(sampler, MeasurementParameters(), controller, interaction)
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
    trickle_progress = sampler.take_average_measurement.call_args.kwargs["on_progress"]
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
    sampler = MagicMock(spec=PowerSampler)
    sampler.take_measurement.return_value = MeasurementResult(power=10.5, voltages=[])
    interaction = MagicMock(spec=RunInteraction)
    runner = ChargingRunner(sampler, MeasurementParameters(fast_test_mode=True), controller, interaction)
    request = ChargingMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyChargingControllerSpec(),
        charging_device_type=ChargingDeviceType.VACUUM_ROBOT,
        fast_test_mode=True,
    )

    runner.run(request, "")

    assert sampler.take_measurement.call_count == 2
    sampler.take_average_measurement.assert_not_called()
    interaction.wait.assert_not_called()


def test_generated_profile_uses_discovered_battery_sensor_state() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.battery_level_attribute = None
    runner = ChargingRunner(MagicMock(spec=PowerSampler), MeasurementParameters(), controller)
    model_data = runner._build_model_json_data({50: [10.0]}, ChargingDeviceType.VACUUM_ROBOT)  # noqa: SLF001

    assert model_data["linear_config"] == {"calibrate": ["50 -> 10.0"]}


def test_generated_profile_keeps_battery_level_attribute_fallback() -> None:
    controller = MagicMock(spec=ChargingController)
    controller.battery_level_attribute = ATTR_BATTERY_LEVEL
    runner = ChargingRunner(MagicMock(spec=PowerSampler), MeasurementParameters(), controller)
    model_data = runner._build_model_json_data({50: [10.0]}, ChargingDeviceType.VACUUM_ROBOT)  # noqa: SLF001

    assert model_data["linear_config"] == {
        "attribute": ATTR_BATTERY_LEVEL,
        "calibrate": ["50 -> 10.0"],
    }
