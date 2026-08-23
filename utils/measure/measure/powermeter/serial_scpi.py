from abc import abstractmethod
import time

import serial

from measure.powermeter.const import OwonOwh98xxChannelType
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class SerialScpiPowerMeter(PowerMeter):
    # Tested on Linux only
    def __init__(self, port: str, baudrate: int, timeout: float = 5.0) -> None:
        # Timeout so the readline cannot hang indefinitely
        try:
            self._serial = serial.Serial(port, baudrate, timeout=timeout, exclusive=True)
        except (ValueError, serial.SerialException) as error:
            raise PowerMeterError(error) from error
        self.manufacturer, self.model, self.serial, self.software_version = self._identify()

    def identify_request(self) -> bytes:
        """
        The bytes to send for the identify request
        Can be overwritten because serial devices are sometimes weird
        """
        return b"*IDN?\n"

    @abstractmethod
    def power_request(self) -> bytes:
        """The bytes to send for the power request"""

    @abstractmethod
    def voltage_request(self) -> bytes:
        """The bytes to send for the voltage request"""

    def _retrieve_data(self, request: bytes) -> bytes:
        try:
            self._serial.write(request)
        except serial.SerialTimeoutException as error:
            raise PowerMeterError(error) from error
        return self._serial.readline()

    def _bytes_to_float(self, data: bytes) -> float:
        try:
            return float(data.strip().decode())
        except (ValueError, OverflowError) as error:
            raise PowerMeterError(error) from error

    def _retrieve_float(self, request: bytes) -> float:
        response = self._retrieve_data(request)
        return self._bytes_to_float(response)

    def _identify(self) -> tuple[bytes, bytes, bytes, bytes]:
        response = self._retrieve_data(self.identify_request())
        try:
            manufacturer, model, serial, software_version = response.strip().split(b",")
        except ValueError as error:
            raise PowerMeterError(error) from error
        return manufacturer, model, serial, software_version

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        power = self._retrieve_float(self.power_request())
        if include_voltage and self.has_voltage_support:
            voltage = self._retrieve_float(self.voltage_request())
        return PowerMeasurementResult(
            power=power, updated=time.time(), voltage=voltage if include_voltage and self.has_voltage_support else None
        )


class OwonOwh98xxPowerMeter(SerialScpiPowerMeter):
    # Based on https://storage.eleshop.eu/files/OWH9811_Power_Meter_Programming_Manual.pdf

    def __init__(self, port: str, baudrate: int, timeout: float, channel: OwonOwh98xxChannelType) -> None:
        super().__init__(port, baudrate, timeout)

        self.channel = int(channel)

        if self.manufacturer != b"OWON":
            raise PowerMeterError("Not an OWON device")
        if not self.model.startswith(b"OWH98"):
            raise PowerMeterError("Not an OWON OWH98xx series device")

        if self._retrieve_data(self.power_request()) == b"\n":
            # If the device's local controls are not locked, it will not return the value
            raise PowerMeterError("Cannot retrieve power, is local locked?")

    def _retrieve_float(self, request: bytes) -> float:
        # It has a special case for zero, hence the override
        response = self._retrieve_data(request).strip()
        return 0 if response == b"----" else self._bytes_to_float(response)

    def power_request(self) -> bytes:
        return f":MEAS:POW:REAL:ELEMENT{self.channel}?\n".encode()

    def voltage_request(self) -> bytes:
        return f":MEAS:VOLT:ELEMENT{self.channel}?\n".encode()

    def has_voltage_support(self) -> bool:
        return True
