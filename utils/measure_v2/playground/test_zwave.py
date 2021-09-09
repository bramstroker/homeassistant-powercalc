import asyncio
import websockets
import aiohttp
from zwave_js_server.client import Client

ZWAVE_JS_URL = "ws://192.168.178.99:3000"
NODE_ID = 28

async def connect(url) -> None:
    """Connect to the server."""
    async with aiohttp.ClientSession() as session:
        async with Client(url, session) as client:

            driver_ready = asyncio.Event()
            asyncio.create_task(on_driver_ready(client, driver_ready))

            await client.listen(driver_ready)


async def on_driver_ready(client: Client, driver_ready: asyncio.Event) -> None:
    """Act on driver ready."""
    await driver_ready.wait()

    assert client.driver

    node = client.driver.controller.nodes.get(NODE_ID)
    #todo exception when node is none

    node.on("value updated", on_value_updated)

def on_value_updated(event: dict) -> None:
    """Log node value changes."""
    value = event["value"]
    if value.metadata.unit != "W":
        return
    power = value.value
    print(power)

#asyncio.get_event_loop().run_until_complete(hello())
asyncio.run(connect(ZWAVE_JS_URL))