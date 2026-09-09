import asyncio
import time

from kasa import Credentials, Discover, Module

from measure.powermeter.errors import PowerMeterError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class KasaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str, *, credentials: tuple[str, str] | None = None) -> None:
        self._device_ip = device_ip
        self._credentials = Credentials(*credentials) if credentials is not None else None

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a new Kasa or Tapo power reading. Optionally include voltage."""
        power, voltage = asyncio.run(self.async_read_power_meter())

        if include_voltage:
            return PowerMeasurementResult(power=power, voltage=voltage, updated=time.time())
        return PowerMeasurementResult(power=power, updated=time.time())

    async def async_read_power_meter(self) -> tuple[float, float | None]:
        device = await Discover.discover_single(self._device_ip, credentials=self._credentials)
        if device is None:
            raise PowerMeterError(f"No Kasa or Tapo device was discovered at {self._device_ip}")
        try:
            await device.update()
            energy = device.modules.get(Module.Energy)
            if energy is None:
                raise PowerMeterError("The Kasa or Tapo device does not provide energy monitoring")
            voltage = getattr(energy, "voltage", None)
            return float(energy.current_consumption), float(voltage) if voltage is not None else None
        finally:
            await device.disconnect()

    def has_voltage_support(self) -> bool:
        return True
