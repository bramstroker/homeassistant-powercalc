from unittest.mock import MagicMock, patch

from measure.powermeter.const import OwonOwh98xxChannelType
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.serial_scpi import OwonOwh98xxPowerMeter
import pytest
from serial import SerialException


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

    assert meter._retrieve_float(b"") == 1.0  # noqa: SLF001
    serial.readline.assert_called_once()


def test_owh98xx_retrieve_float_zero() -> None:
    # Special case for the Owon OWH series
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"----\n")

    assert meter._retrieve_float(b"") == 0.0  # noqa: SLF001
    serial.readline.assert_called_once()


def test_owh98xx_retrieve_float_failure() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"\n")

    with pytest.raises(PowerMeterError):
        meter._retrieve_float(b"")  # noqa: SLF001

    serial.readline.assert_called_once()


def test_owh98xx_get_power_no_voltage() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(return_value=b"5.0\n")

    measurement = meter.get_power(False)

    assert measurement.power == 5.0
    assert measurement.voltage is None
    serial.readline.assert_called_once()


def test_owh98xx_get_power_with_voltage() -> None:
    serial = MagicMock()
    serial.readline = MagicMock(return_value=b"OWON,OWH9811,SERIAL,FV:V1.1.0\n")

    with patch("serial.Serial", return_value=serial):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, 1)

    serial.readline = MagicMock(side_effect=[b"1.0\n", b"2.0\n"])

    measurement = meter.get_power(True)

    assert measurement.power == 1.0
    assert measurement.voltage == 2.0
    assert serial.readline.call_count == 2


@pytest.mark.parametrize("error", [ValueError("Invalid baudrate"), SerialException("Port unavailable")])
def test_serial_meter_reports_connection_failure(error: Exception) -> None:
    with patch("serial.Serial", side_effect=error), pytest.raises(PowerMeterError) as raised:
        OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, OwonOwh98xxChannelType.CHANNEL1)

    assert raised.value.__cause__ is error


@pytest.mark.parametrize(
    "responses,message",
    [
        ([b"invalid identification\n"], None),
        ([b"OTHER,OWH9811,SERIAL,V1\n"], "Not an OWON device"),
        ([b"OWON,OTHER,SERIAL,V1\n"], "Not an OWON OWH98xx series device"),
        ([b"OWON,OWH9811,SERIAL,V1\n", b"\n"], "Cannot retrieve power"),
    ],
)
def test_serial_meter_rejects_invalid_or_locked_device(responses: list[bytes], message: str | None) -> None:
    connection = MagicMock()
    connection.readline.side_effect = responses

    with patch("serial.Serial", return_value=connection), pytest.raises(PowerMeterError, match=message):
        OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, OwonOwh98xxChannelType.CHANNEL1)


@pytest.mark.parametrize("operation", ["write", "readline"])
def test_serial_meter_reports_io_failure(operation: str) -> None:
    connection = MagicMock()
    connection.readline.side_effect = [b"OWON,OWH9811,SERIAL,V1\n", b"1.0\n"]
    with patch("serial.Serial", return_value=connection):
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 115200, 5.0, OwonOwh98xxChannelType.CHANNEL1)
    error = SerialException("Device disconnected")
    getattr(connection, operation).side_effect = error

    with pytest.raises(PowerMeterError) as raised:
        meter.get_power()

    assert raised.value.__cause__ is error


def test_serial_meter_reads_selected_channel_power_and_voltage() -> None:
    connection = MagicMock()
    connection.readline.side_effect = [b"OWON,OWH9811,SERIAL,V1\n", b"1.0\n", b"----\n", b"230.5\n"]
    with patch("serial.Serial", return_value=connection) as constructor:
        meter = OwonOwh98xxPowerMeter("/dev/ttyUSB0", 9600, 2.5, OwonOwh98xxChannelType.CHANNEL2)
    connection.write.reset_mock()

    result = meter.get_power(include_voltage=True)

    constructor.assert_called_once_with("/dev/ttyUSB0", 9600, timeout=2.5, exclusive=True)
    assert result.power == 0
    assert result.voltage == 230.5
    assert [call.args[0] for call in connection.write.call_args_list] == [
        b":MEAS:POW:REAL:ELEMENT2?\n",
        b":MEAS:VOLT:ELEMENT2?\n",
    ]
    assert meter.has_voltage_support() is True
