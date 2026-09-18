from unittest.mock import patch

from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult
from measure.powermeter.tuya import TuyaPowerMeter
import pytest


def test_tuya_passes_connection_settings_and_reads_power() -> None:
    meter = TuyaPowerMeter("device-id", "192.0.2.10", "device-key", "3.4")

    with (
        patch("measure.powermeter.tuya.tuyapower.deviceInfo", return_value=("device", 12.5, 230, 0.1, "OK")) as read,
        patch("time.time", return_value=1234),
    ):
        result = meter.get_power()

    assert result == PowerMeasurementResult(power=12.5, updated=1234)
    read.assert_called_once_with("device-id", "192.0.2.10", "device-key", "3.4")
    assert not meter.has_voltage_support()


def test_tuya_rejects_unsuccessful_reading() -> None:
    meter = TuyaPowerMeter("device-id", "192.0.2.10", "device-key")

    with (
        patch("measure.powermeter.tuya.tuyapower.deviceInfo", return_value=("device", 0, 0, 0, "Offline")),
        pytest.raises(PowerMeterError, match="successful power reading"),
    ):
        meter.get_power()


def test_tuya_rejects_voltage_before_contacting_device() -> None:
    meter = TuyaPowerMeter("device-id", "192.0.2.10", "device-key")

    with patch("measure.powermeter.tuya.tuyapower.deviceInfo") as read, pytest.raises(UnsupportedFeatureError):
        meter.get_power(include_voltage=True)

    read.assert_not_called()
