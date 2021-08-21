from __future__ import annotations, print_function, unicode_literals

import asyncio
import csv
import json
import os
from typing import Iterator

import aiohttp
import aiohue
import asyncstdlib as a
from aiohue.lights import Light
from PyInquirer import prompt
import tuyapower

MODE_HS = "hs"
MODE_COLOR_TEMP = "color_temp"
MODE_BRIGHTNESS = "brightness"
HUE_BRIDGE_USERNAME = "huepower"
CSV_HEADERS = {
    MODE_HS: ["bri", "hue", "sat", "watt"],
    MODE_COLOR_TEMP: ["bri", "mired", "watt"],
    MODE_BRIGHTNESS: ["bri", "watt"]
}

# Change the params below
device_id="aaaaaaaaad89682385bbb"
device_ip="192.168.1.148"
device_key="aaaaaaaae1b8abb"
device_ver="3.3"

HUE_BRIDGE_IP = "192.168.1.21"
SLEEP_TIME = 2  # time between changing the light params and taking the measurement
SLEEP_TIME_HUE = 5  # time to wait between each increase in hue
SLEEP_TIME_SAT = 10  # time to wait between each increase in saturation

# Change this when the script crashes due to connectivity issues, so you don't have to start all over again
START_BRIGHTNESS = 1
MAX_BRIGHTNESS = 255


def get_power():
    (on, w, mA, V, err) = tuyapower.deviceInfo(device_id, device_ip, device_key, device_ver)
    if(err == "OK"):
        return w
    else:
        return -1



async def main():

    async with aiohttp.ClientSession() as aiohttp_session:

        hue_bridge = await initialize_hue_bridge(aiohttp_session)
        light_list = []
        for light_id in hue_bridge.lights:
            light = hue_bridge.lights[light_id]
            light_list.append({"key": light_id, "value": light_id, "name": light.name})

        answers = prompt(get_questions(light_list))

        light_id = answers["light"]
        color_mode = answers["color_mode"]

        light = hue_bridge.lights[light_id]
        export_directory = os.path.join(
            os.path.dirname(__file__),
            "export",
            light.modelid
        )
        if not os.path.exists(export_directory):
            os.makedirs(export_directory)

        if answers["generate_model_json"]:
            standby_usage = await measure_standby_usage(light)
            write_model_json(directory=export_directory, standby_usage=standby_usage, name=answers["model_name"])

        with open(f"{export_directory}/{color_mode}.csv", "w") as csv_file:
            csv_writer = csv.writer(csv_file)

            await light.set_state(on=True, bri=1)

            # Initially wait longer so the plug can settle
            print("Start taking measurements for color mode: ", color_mode)
            print("Waiting 10 seconds...")
            await asyncio.sleep(10)

            csv_writer.writerow(CSV_HEADERS[color_mode])
            async for count, variation in a.enumerate(get_variations(color_mode, light)):
                print("Changing light to: ", variation)
                await light.set_state(**variation)
                await asyncio.sleep(SLEEP_TIME)
                power = get_power()
                print("Measured power: ", power)
                print()
                row = list(variation.values())
                row.append(power)
                csv_writer.writerow(row)
                if count % 100 == 0:
                    csv_file.flush()

            csv_file.close()


async def get_variations(color_mode: str, light: Light):
    if color_mode == MODE_HS:
        async for v in get_hs_variations():
            yield v
    elif color_mode == MODE_COLOR_TEMP:
        async for v in  get_ct_variations(light):
            yield v
    else:
        async for v in get_brightness_variations():
            yield v


async def get_ct_variations(light: Light):
    if "ct" in light.controlcapabilities:
        min_mired = light.controlcapabilities["ct"]["min"]
        max_mired = light.controlcapabilities["ct"]["max"]
    else:
        min_mired = 150
        max_mired = 500

    if max_mired > 500:
        max_mired = 500

    if min_mired < 150:
        min_mired = 150

    for bri in inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 5):
        for mired in inclusive_range(min_mired, max_mired, 10):
            yield {"bri": bri, "ct": mired}


async def get_hs_variations():
    for bri in inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 10):
        for sat in inclusive_range(1, 254, 10):
            await asyncio.sleep(SLEEP_TIME_SAT)
            for hue in inclusive_range(1, 65535, 2000):
                await asyncio.sleep(SLEEP_TIME_HUE)
                yield {"bri": bri, "hue": hue, "sat": sat}


async def get_brightness_variations():
    for bri in inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 1):
        yield {"bri": bri}


def inclusive_range(start: int, end: int, step: int) -> Iterator[int]:
    i = start
    while i < end:
        yield i
        i += step
    yield end


def write_model_json(directory: str, standby_usage: float, name: str):
    json_data = json.dumps({
        "name": name,
        "standby_usage": standby_usage,
        "supported_modes": [
            "lut"
        ]
    })
    json_file = open(os.path.join(directory, "model.json"), "w")
    json_file.write(json_data)
    json_file.close()


async def measure_standby_usage(light: Light) -> float:
    await light.set_state(on=False)
    print("Measuring standby usage. Waiting for 5 seconds...")
    await asyncio.sleep(5)
    return get_power()


def get_questions(light_list) -> list[dict]:
    return [
        {
            'type': 'list',
            'name': 'color_mode',
            'message': 'Select the color mode?',
            'default': MODE_HS,
            'choices': [MODE_HS, MODE_COLOR_TEMP, MODE_BRIGHTNESS],
        },
        {
            'type': 'list',
            'name': 'light',
            'message': 'Select the light?',
            'choices': light_list
        },
        {
            'type': 'confirm',
            'message': 'Do you want to generate model.json?',
            'name': 'generate_model_json',
            'default': True,
        },
        {
            'type': 'input',
            'name': 'model_name',
            'message': 'Specify the full light model name',
            'when': lambda answers: answers['generate_model_json']
        },
    ]


async def initialize_hue_bridge(websession) -> aiohue.Bridge:
    f = open("bridge_user.txt", "r+")

    bridge = aiohue.Bridge(host=HUE_BRIDGE_IP, websession=websession)

    authenticated_user = f.read()
    if len(authenticated_user) > 0:
        bridge.username = authenticated_user

    try:
        await bridge.initialize()
    except aiohue.Unauthorized as err:
        print("Please click the link button on the bridge, than hit enter..")
        input()
        await bridge.create_user(HUE_BRIDGE_USERNAME)
        await bridge.initialize()
        f.write(bridge.username)

    f.close()

    return bridge


if __name__ == "__main__":
    asyncio.run(main())
