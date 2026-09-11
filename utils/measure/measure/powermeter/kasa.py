import asyncio
import time

from kasa import AuthenticationError, Credentials, Device, DeviceConfig, Discover, Module

from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class KasaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str, *, credentials: tuple[str, str] | None = None) -> None:
        self._device_ip = device_ip
        self._credentials = Credentials(*credentials) if credentials is not None else None
        self._device_config: DeviceConfig | None = None
        self._voltage_supported: bool | None = None

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a new Kasa or Tapo power reading. Optionally include voltage."""
        power, voltage = asyncio.run(self.async_read_power_meter())

        if include_voltage:
            if voltage is None:
                raise UnsupportedFeatureError("The Kasa or Tapo device does not provide voltage measurements")
            return PowerMeasurementResult(power=power, voltage=voltage, updated=time.time())
        return PowerMeasurementResult(power=power, updated=time.time())

    async def async_read_power_meter(self) -> tuple[float, float | None]:
        device = await self._connect()
        try:
            try:
                await device.update()
            except AuthenticationError as error:
                if self._credentials is None:
                    message = "This Kasa or Tapo device requires TP-Link account credentials"
                else:
                    message = "TP-Link account authentication failed; verify the configured credentials"
                raise PowerMeterError(message) from error
            energy = device.modules.get(Module.Energy)
            if energy is None:
                raise PowerMeterError("The Kasa or Tapo device does not provide energy monitoring")
            voltage = getattr(energy, "voltage", None)
            self._voltage_supported = voltage is not None
            return float(energy.current_consumption), float(voltage) if voltage is not None else None
        finally:
            await device.disconnect()

    async def _connect(self) -> Device:
        """Discover once, then reconnect directly with the discovered protocol settings."""
        if self._device_config is not None:
            return await Device.connect(config=self._device_config)

        device = await Discover.discover_single(self._device_ip, credentials=self._credentials)
        if device is None:
            raise PowerMeterError(f"No Kasa or Tapo device was discovered at {self._device_ip}")
        # A DeviceConfig is independent of the live connection and can safely cross the
        # short-lived event loops created by get_power(). It retains the detected protocol,
        # transport, and credentials, so later samples do not require UDP discovery.
        self._device_config = DeviceConfig.from_dict(device.config.to_dict())
        return device

    def has_voltage_support(self) -> bool:
        if self._voltage_supported is None:
            # The initial probe also caches the connection configuration, so the first
            # real sample connects directly instead of broadcasting discovery again.
            asyncio.run(self.async_read_power_meter())
        return bool(self._voltage_supported)
