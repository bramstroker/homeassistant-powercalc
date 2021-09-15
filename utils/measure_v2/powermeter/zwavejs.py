from __future__ import annotations

import time

from zwave_js_server.const import CommandClass
from .powermeter import PowerMeasurementResult, PowerMeter
from .errors import PowerMeterError
from typing import cast

import asyncio
import aiohttp
import threading
import queue
from zwave_js_server.client import Client
from zwave_js_server.model.driver import Driver


class ZwaveJsPowerMeter(PowerMeter):
    def __init__(self, ws_url: str):
        self._power: float = None
        self._ws_url: str = ws_url
        self._node_id: int = 28
        self._connected: bool = False
        self.session = None
        self._command_queue = queue.Queue()
        #thread = threading.Thread(target=self.start_monitor)
        #thread.start()

    async def setup(self):
        return

    def start_monitor(self):
        asyncio.run(self.connect())

    async def connect(self):
        """Connect to the server."""
        self.session = aiohttp.ClientSession()
        self._client = Client(self._ws_url, self.session)

        #self._client = client
        #driver_ready = asyncio.Event()
        #asyncio.create_task(self.on_driver_ready(client, driver_ready))

        await self._client.connect()
        await self._client.set_api_schema()
        await self._client._send_json_message(
            {
                "command": "driver.get_log_config",
                "messageId": "get-initial-log-config",
            }
        )
        log_msg = await self._client._receive_json_or_raise()

        # this should not happen, but just in case
        if not log_msg["success"]:
            await self._client.close()
            #raise FailedCommand(log_msg["messageId"], log_msg["errorCode"])

        # send start_listening command to the server
        # we will receive a full state dump and from now on get events
        await self._client._send_json_message(
            {"command": "start_listening", "messageId": "listen-id"}
        )

        state_msg = await self._client._receive_json_or_raise()

        if not state_msg["success"]:
            await self._client.close()
            #raise FailedCommand(state_msg["messageId"], state_msg["errorCode"])

        loop = asyncio.get_running_loop()
        driver = cast(
            Driver,
            await loop.run_in_executor(
                None,
                Driver,
                self._client,
                state_msg["result"]["state"],
                log_msg["result"]["config"],
            ),
        )
        self.driver = driver
        self._connected = True
                
    async def get_power(self) -> PowerMeasurementResult:
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
        power = PowerMeasurementResult(
            power_value,
            time.time()
        )

        if power is None:
            raise PowerMeterError("No power reading from Zwave plug yet")

        return power

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

        power_values = [v for v in node.values.values() if v.metadata.unit == "W"]
        self.node_value = power_values[0]
        #todo exception when node is none

        while True:
            item = self._command_queue.get()
            self._command_queue.task_done()

        node.on("value updated", self.on_value_updated)

    def on_value_updated(self, event: dict) -> None:
        """Log node value changes."""
        value = event["value"]
        if value != self.node_value:
            return

        print("retrieved power")
        power = value.value
        self._power = PowerMeasurementResult(
            power,
            time.time()
        )
