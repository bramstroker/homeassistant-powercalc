import asyncio
from pprint import pprint
import aiohttp
import aiohue
import aioshelly
import asyncio
import csv

MODE_HS = "hs"
MODE_COLOR_TEMP = "color_temp"
SHELLY_IP = "192.168.178.254"
HUE_BRIDGE_IP = "192.168.178.44"
HUE_BRIDGE_USERNAME="huepower"
MODE = MODE_HS
SLEEP_TIME=2

async def main():
    options = aioshelly.ConnectionOptions(SHELLY_IP)

    csvFile = open('measurements.csv', 'w')
    csvWriter = csv.writer(csvFile)

    async with aiohttp.ClientSession() as aiohttp_session, aioshelly.COAP() as coap_context:
        try:
            device = await asyncio.wait_for(
                aioshelly.Device.create(aiohttp_session, coap_context, options), 5
            )
        except asyncio.TimeoutError:
            print("Timeout connecting to", SHELLY_IP)
            return

        powermeter = device.blocks[0]

        hue_bridge = await initialize_hue_bridge(aiohttp_session)

        for id in hue_bridge.lights:
            light = hue_bridge.lights[id]
            print('{}: {}: {}'.format(id, light.name, 'on' if light.state['on'] else 'off'))
	
        light_id = input("Enter light id: ")

        light = hue_bridge.lights[light_id]
        await light.set_state(on=True, bri=1)

        #Initialy wait longer so the Shelly plug can settle
        await asyncio.sleep(10) 

        if (MODE == MODE_HS):
            for bri in range(1, 254, 10):
                for hue in range(0, 65535, 2000):
                    for sat in range(0, 254, 10):
                        print('Setting hsl to: {}:{}:{}', hue, sat, bri)
                        await light.set_state(bri=bri, hue=hue, sat=sat)
                        await asyncio.sleep(SLEEP_TIME)
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
        else:
            for bri in range(1, 254, 5):
                for mired in range(150, 500, 10):
                    print('Setting bri:mired to: {}:{}', bri, mired)
                    await light.set_state(bri=bri, ct=mired)
                    await asyncio.sleep(SLEEP_TIME)
                    power = powermeter.current_values()["power"]
                    print(power)
                    print()
                    csvWriter.writerow(
                        [
                            bri,
                            mired,
                            power
                        ]
                    )
                    csvFile.flush()

        csvFile.close()

async def initialize_hue_bridge(websession) -> aiohue.Bridge:
    f = open("bridge_user.txt", "w+")

    bridge = aiohue.Bridge(
        host=HUE_BRIDGE_IP,
        websession=websession
    )

    authenticated_user = f.read()
    if (len(authenticated_user) > 0):
        bridge.username = authenticated_user

    try:
        await bridge.initialize()
    except (aiohue.Unauthorized) as err:
        print("Please click the link button on the bridge, than hit enter..")
        input()
        await bridge.create_user("huepower")
        await bridge.initialize()
        f.write(bridge.username)
        
    f.close()

    return bridge

if __name__ == "__main__":
    asyncio.run(main())
