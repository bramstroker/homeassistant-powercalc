from unittest.mock import MagicMock

from measure.controller.fan.dummy import DummyFanController
from measure.controller.fan.spec import DummyFanControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import FanMeasurementRequest
from measure.runner.fan import FanRunner
from measure.util.measure_util import MeasurementResult, MeasureUtil


def test_run(export_path: str) -> None:
    measure_util_mock = MagicMock(MeasureUtil)
    measure_util_mock.take_average_measurement.return_value = MeasurementResult(power=10.50, voltages=[])
    runner = FanRunner(measure_util_mock, DummyFanController())
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
