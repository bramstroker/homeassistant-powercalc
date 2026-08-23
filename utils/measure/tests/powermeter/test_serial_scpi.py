import serial
from unittest.mock import MagicMock, patch

from measure.powermeter.errors import PowerMeterError
from measure.powermeter.serial_scpi import OwonOwh98xxPowerMeter
import pytest


def test_owh98xx_identify() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        # Identify is called in the init
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    assert meter.manufacturer == b"OWON"
    assert meter.model == b"OWH9811"
    assert meter.serial == b"SERIAL"
    assert meter.software_version == b"FV:V1.1.0"


def test_owh98xx_retrieve_float() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"1.0\n")

    assert 1.0 == meter._retrieve_float(b"")
    serial.readline.assert_called_once()


def test_owh98xx_retrieve_float_zero() -> None:
    # Special case for the Owon OWH series
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"----\n")

    assert 0.0 == meter._retrieve_float(b"")
    serial.readline.assert_called_once()


def test_owh98xx_retrieve_float_failure() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"\n")

    with pytest.raises(PowerMeterError):
        meter._retrieve_float(b"")

    serial.readline.assert_called_once()


def test_owh98xx_get_power_no_voltage() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"5.0\n")

    measurement = meter.get_power(False)

    assert measurement.power == 5.0
    assert measurement.voltage == None
    serial.readline.assert_called_once()


def test_owh98xx_get_power_with_voltage() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    # Ugly way of giving back different values based on if it's the first call
    global firstCall
    firstCall = True
    def readline_side_effect():
        global firstCall
        if firstCall:
            firstCall = False
            return b"1.0\n"
        else:
            return b"2.0\n"
    serial.readline = MagicMock(side_effect=readline_side_effect)

    measurement = meter.get_power(True)

    assert measurement.power == 1.0
    assert measurement.voltage == 2.0
    assert serial.readline.call_count == 2

