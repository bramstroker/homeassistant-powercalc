from __future__ import annotations

import time
from .powermeter import PowerMeasurementResult, PowerMeter
from .errors import PowerMeterError

import asyncio
import aiohttp
import threading
from zwave_js_server.client import Client


class ZwaveJsPowerMeter(PowerMeter):
    def __init__(self, ws_url: str):
        self._power: float = None
        self._ws_url: str = ws_url
        self._node_id: int = 28
        
        thread = threading.Thread(target=self.start_monitor)
        thread.start()

    async def setup(self):
        return

    def start_monitor(self):
        asyncio.run(self.connect())

    async def connect(self):
        """Connect to the server."""
        async with aiohttp.ClientSession() as session:
            async with Client(self._ws_url, session) as client:

                driver_ready = asyncio.Event()
                asyncio.create_task(self.on_driver_ready(client, driver_ready))

                await client.listen(driver_ready)
                
    def get_power(self) -> PowerMeasurementResult:
        if self._power is None:
            raise PowerMeterError("No power reading from Zwave plug yet")

        return self._power

    def get_questions(self) -> list[dict]:
        return [
        ]

    def process_answers(self, answers):
        return
        self._node_id = answers["powermeter_zwave_node_id"]

    async def on_driver_ready(self, client: Client, driver_ready: asyncio.Event) -> None:
        """Act on driver ready."""
        await driver_ready.wait()
        print("driver ready")
        assert client.driver

        node = client.driver.controller.nodes.get(self._node_id)
        #todo exception when node is none

        node.on("value updated", self.on_value_updated)

    def on_value_updated(self, event: dict) -> None:
        """Log node value changes."""
        value = event["value"]
        unit = value.metadata.unit
        if unit != "W":
            return
        print("retrieved power")
        power = value.value
        self._power = PowerMeasurementResult(
            power,
            time.time()
        )
