from __future__ import annotations

import time
from .powermeter import PowerMeasurementResult, PowerMeter

import asyncio
import aiohttp
from zwave_js_server.client import Client


class ZwaveJsPowerMeter(PowerMeter):
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._node_id = 28
        #loop = asyncio.get_event_loop()
        #loop.run_in_executor(None, self.connect)
        #asyncio.run(self.connect())

    async def setup(self):
        """Connect to the server."""
        async with aiohttp.ClientSession() as session:
            async with Client(self._ws_url, session) as client:

                driver_ready = asyncio.Event()
                print("creating tasks")
                asyncio.create_task(self.on_driver_ready(client, driver_ready))

                asyncio.create_task(client.listen(driver_ready))
                
    def get_power(self) -> PowerMeasurementResult:
        return PowerMeasurementResult(
            0,
            time.time()
        )

    def get_questions(self) -> list[dict]:
        return [
        ]

    def process_answers(self, answers):
        return
        self._node_id = answers["powermeter_zwave_node_id"]

    async def connect(self) -> None:
        """Connect to the server."""
        async with aiohttp.ClientSession() as session:
            async with Client(self._ws_url, session) as client:

                driver_ready = asyncio.Event()
                print("creating tasks")
                asyncio.create_task(self.on_driver_ready(client, driver_ready))

                asyncio.create_task(client.listen(driver_ready))


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
        power = value.value
        print(power)
