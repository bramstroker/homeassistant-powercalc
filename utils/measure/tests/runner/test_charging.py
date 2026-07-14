from unittest.mock import MagicMock

from measure.controller.charging.const import ChargingDeviceType
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

    assert [call.args[0] for call in interaction.operating_point.call_args_list] == [
        {"type": "charging", "battery_level": 99, "charging": True},
        {"type": "charging", "battery_level": 99, "charging": True},
        {"type": "charging", "battery_level": 100, "charging": True},
    ]
