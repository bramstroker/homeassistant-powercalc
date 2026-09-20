from unittest.mock import MagicMock, patch

from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.mystrom import MyStromPowerMeter
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.powermeter.tasmota import TasmotaPowerMeter
import pytest


@pytest.mark.parametrize(
    "meter_type,payload,endpoint",
    [
        (MyStromPowerMeter, {"power": "12.5"}, "/report"),
        (TasmotaPowerMeter, {"StatusSNS": {"ENERGY": {"Power": "12.5"}}}, "/cm?cmnd=STATUS+8"),
    ],
)
def test_http_meter_reads_power_with_timestamp(
    meter_type: type[PowerMeter],
    payload: dict[str, object],
    endpoint: str,
) -> None:
    response = MagicMock()
    response.json.return_value = payload
    meter = meter_type("192.0.2.10")

    with patch("requests.get", return_value=response) as get, patch("time.time", return_value=1234):
        result = meter.get_power()

    assert result == PowerMeasurementResult(power=12.5, updated=1234)
    get.assert_called_once_with(f"http://192.0.2.10{endpoint}", timeout=10)
    assert not meter.has_voltage_support()


@pytest.mark.parametrize("meter_type", [MyStromPowerMeter, TasmotaPowerMeter])
def test_http_meter_rejects_missing_power(meter_type: type[PowerMeter]) -> None:
    response = MagicMock()
    response.json.return_value = {}
    meter = meter_type("192.0.2.10")

    with (
        patch("requests.get", return_value=response),
        pytest.raises(PowerMeterError, match="Unexpected JSON") as raised,
    ):
        meter.get_power()

    assert isinstance(raised.value.__cause__, KeyError)


@pytest.mark.parametrize("meter_type", [MyStromPowerMeter, TasmotaPowerMeter])
def test_http_meter_rejects_voltage_before_contacting_device(meter_type: type[PowerMeter]) -> None:
    meter = meter_type("192.0.2.10")

    with patch("requests.get") as get, pytest.raises(UnsupportedFeatureError, match="Voltage measurement"):
        meter.get_power(include_voltage=True)

    get.assert_not_called()
