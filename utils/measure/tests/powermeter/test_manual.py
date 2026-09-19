from unittest.mock import call, patch

from measure.powermeter.manual import ManualPowerMeter
import pytest


def test_manual_meter_reads_power_only() -> None:
    with (
        patch("builtins.input", return_value="12.75") as prompt,
        patch("measure.powermeter.manual.time.time", return_value=100),
    ):
        result = ManualPowerMeter().get_power()

    assert result.power == 12.75
    assert result.voltage is None
    assert result.updated == 100
    prompt.assert_called_once_with("Input power measurement: ")


def test_manual_meter_reads_power_and_voltage() -> None:
    meter = ManualPowerMeter()
    with patch("builtins.input", side_effect=["12.75", "230.5"]) as prompt:
        result = meter.get_power(include_voltage=True)

    assert result.power == 12.75
    assert result.voltage == 230.5
    assert meter.has_voltage_support() is True
    assert prompt.call_args_list == [call("Input power measurement: "), call("Input voltage measurement: ")]


@pytest.mark.parametrize("readings", [["invalid", "230"], ["12", "invalid"]])
def test_manual_meter_rejects_invalid_readings(readings: list[str]) -> None:
    with (
        patch("builtins.input", side_effect=readings),
        pytest.raises(ValueError, match="could not convert string to float"),
    ):
        ManualPowerMeter().get_power(include_voltage=True)


def test_manual_meter_diagnostics_use_entered_power() -> None:
    with patch("builtins.input", return_value="12.75"), patch("measure.powermeter.manual.time.time", return_value=100):
        sample = ManualPowerMeter().diagnostic_sample()

    assert sample.power == 12.75
    assert sample.raw_value == "12.75"
    assert sample.reported_at == 100
