from __future__ import annotations

from kasa import SmartPlug
import asyncio
from .powermeter import PowerMeter

class KasaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str):
        self._smartplug = SmartPlug(device_ip)

    def get_power(self) -> float:
        loop = asyncio.get_event_loop()
        power = loop.run_until_complete(self.async_read_power_meter())
        return power
    
    async def async_read_power_meter(self):
        await self._smartplug.update()
        return self._smartplug.emeter_realtime['power']
