from __future__ import annotations

import asyncio
import time
from typing import Any

from kasa import SmartPlug

from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class KasaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str) -> None:
        self._smartplug = SmartPlug(device_ip)

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a new power reading from the Kasa device. Optionally include voltage."""
        loop = asyncio.get_event_loop()
        power, voltage = loop.run_until_complete(self.async_read_power_meter())

        if include_voltage:
            return PowerMeasurementResult(power=power, voltage=voltage, updated=time.time())
        return PowerMeasurementResult(power=power, updated=time.time())

    async def async_read_power_meter(self) -> tuple[float, float | None]:
        from kasa import Module

        await self._smartplug.update()
        energy = self._smartplug.modules[Module.Energy]
        return float(energy.current_consumption), float(energy.voltage)

    def has_voltage_support(self) -> bool:
        return True

    def process_answers(self, answers: dict[str, Any]) -> None:
        pass
