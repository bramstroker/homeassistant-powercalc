import asyncio
from pprint import pprint
import aiohttp
import aioshelly
import asyncio
from aiohue.discovery import discover_nupnp
import csv

async def main():
    ip = "192.168.178.254"
    options = aioshelly.ConnectionOptions(ip)

    csvFile = open('measurements.csv', 'w')
    csvWriter = csv.writer(csvFile)

    async with aiohttp.ClientSession() as aiohttp_session, aioshelly.COAP() as coap_context:
        try:
            device = await asyncio.wait_for(
                aioshelly.Device.create(aiohttp_session, coap_context, options), 5
            )
        except asyncio.TimeoutError:
            print("Timeout connecting to", ip)
            return

        powermeter = device.blocks[0]


        bridges = await discover_nupnp(aiohttp_session)

        bridge = bridges[0]
        await bridge.create_user('aiophue-example')
        #print('Your username is', bridge.username)

        await bridge.initialize()

        #print('Name', bridge.config.name)
        #print('Mac', bridge.config.mac)

        #print()
        #print('Lights:')
        #for id in bridge.lights:
        #    light = bridge.lights[id]
        #    print('{}: {}: {}'.format(id, light.name, 'on' if light.state['on'] else 'off'))

        # Change state of a light.
        light = bridge.lights["12"]
        await light.set_state(on=True)

        for bri in range(71, 254, 10):
            for hue in range(0, 65535, 2000):
                for sat in range(0, 254, 10):
                    print('Setting hsl to: {}:{}:{}', hue, sat, bri)
                    await light.set_state(bri=bri, hue=hue, sat=sat)
                    await asyncio.sleep(2)
                    power = powermeter.current_values()["power"]
                    print(power)
                    print()
                    csvWriter.writerow(
                        [
                            bri,
                            hue,
                            sat,
                            power
                        ]
                    )
                csvFile.flush()

        csvFile.close()

if __name__ == "__main__":
    asyncio.run(main())