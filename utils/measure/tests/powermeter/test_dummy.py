import time

from measure.powermeter.dummy import DummyPowerMeter
import pytest


@pytest.mark.parametrize("include_voltage", [False, True])
def test_dummy_meter_returns_valid_readings_with_optional_voltage(include_voltage: bool) -> None:
    meter = DummyPowerMeter()
    started_at = time.time()

    reading = meter.get_power(include_voltage=include_voltage)

    assert 0 <= reading.power <= 100
    assert reading.power == round(reading.power, 2)
    assert started_at <= reading.updated <= time.time()
    assert reading.voltage == (233.0 if include_voltage else None)
    assert meter.has_voltage_support()
