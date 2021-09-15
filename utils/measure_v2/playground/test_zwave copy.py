from __future__ import annotations

import time

from zwave_js_server.const import CommandClass
from typing import cast

import asyncio
import aiohttp
import threading
import queue
from zwave_js_server.client import Client
from zwave_js_server.model.driver import Driver

ZWAVE_JS_URL = "ws://192.168.1.188:3000"
NODE_ID = 14

class ZwaveJsPowerMeter():
    def __init__(self, ws_url: str):
        self._power: float = None
        self._ws_url: str = ws_url
        self._node_id: int = NODE_ID

        thread = threading.Thread(target=self.start_monitor)
        thread.start()
        thread.join()

    def start_monitor(self):
        asyncio.run(self.connect())

    async def connect(self):
        async with aiohttp.ClientSession() as session:
            async with Client(self._ws_url, session) as client:
                driver_ready = asyncio.Event()
                asyncio.create_task(self.on_driver_ready(client, driver_ready))

                await client.listen(driver_ready)


    async def on_driver_ready(self, client: Client, driver_ready: asyncio.Event) -> None:
        """Act on driver ready."""
        await driver_ready.wait()

        assert client.driver

        node = client.driver.controller.nodes.get(NODE_ID)
        #todo exception when node is none

        node.on("value updated", self.on_value_updated)
                
    async def get_power(self) -> float:
        if self._connected == False:
            await self.connect()

        client = self._client
        client.driver = self.driver

        node = client.driver.controller.nodes.get(self._node_id)

        power_values = [v for v in node.values.values() if v.metadata.unit == "W"]
        self.node_value = power_values[0]
        await node.async_refresh_cc_values(CommandClass(self.node_value.command_class))

        node = client.driver.controller.nodes.get(self._node_id)

        power_values = [v for v in node.values.values() if v.metadata.unit == "W"]
        node_value = power_values[0]

        power_value = node_value.value
        
        return self._power

    async def on_driver_ready(self, client: Client, driver_ready: asyncio.Event) -> None:
        """Act on driver ready."""
        await driver_ready.wait()
        print("driver ready")
        assert client.driver

        node = client.driver.controller.nodes.get(self._node_id)

        power_values = [v for v in node.values.values() if v.metadata.unit == "W"]
        self.node_value = power_values[0]
        #todo exception when node is none

        node.on("value updated", self.on_value_updated)

    def on_value_updated(self, event: dict) -> None:
        """Log node value changes."""
        value = event["value"]
        if value != self.node_value:
            return

        print("retrieved power")
        power = value.value
        print(power)
        self._power = power

ZwaveJsPowerMeter(ZWAVE_JS_URL)