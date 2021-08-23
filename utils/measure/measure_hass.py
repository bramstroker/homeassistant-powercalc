from __future__ import annotations, print_function, unicode_literals

import asyncio
import csv
import json
import os
from typing import Iterator

import aiohttp
import asyncstdlib as a
from PyInquirer import prompt

MODE_HS = "hs"
MODE_COLOR_TEMP = "color_temp"
MODE_BRIGHTNESS = "brightness"
HUE_BRIDGE_USERNAME = "huepower"
CSV_HEADERS = {
    MODE_HS: ["bri", "hue", "sat", "watt"],
    MODE_COLOR_TEMP: ["bri", "mired", "watt"],
    MODE_BRIGHTNESS: ["bri", "watt"]
}

HASS_URL = "http://1.2.3.4/api"
HASS_TOKEN = "tokentokentoken"

SLEEP_TIME = 3  # time between changing the light params and taking the measurement
SLEEP_TIME_HUE = 5  # time to wait between each increase in hue
SLEEP_TIME_SAT = 10  # time to wait between each increase in saturation

# Change this when the script crashes due to connectivity issues, so you don't have to start all over again
START_BRIGHTNESS = 1
MAX_BRIGHTNESS = 255

auth_header = {"Authorization": "Bearer " + HASS_TOKEN}


async def main():
    answers = prompt(get_questions())

    light_id = answers["light_id"]
    power_meter = answers["power_meter"]
    model = answers["model_name"]
    color_mode = answers["color_mode"]

    export_directory = os.path.join(
        os.path.dirname(__file__),
        "export",
        model
    )
    if not os.path.exists(export_directory):
        os.makedirs(export_directory)

    if answers["generate_model_json"]:
        standby_usage = await measure_standby_usage(light_id, power_meter)
        write_model_json(directory=export_directory, standby_usage=standby_usage, name=answers["model_name"])

    with open(f"{export_directory}/{color_mode}.csv", "w") as csv_file:
        csv_writer = csv.writer(csv_file)

        await turn_light_on_bri(light_id, 1)

        # Initially wait longer so the Shelly plug can settle
        print("Start taking measurements for color mode: ", color_mode)
        print("Waiting 10 seconds...")
        await asyncio.sleep(10)

        csv_writer.writerow(CSV_HEADERS[color_mode])
        async for count, variation in a.enumerate(get_variations(color_mode, light_id)):
            print("Changing light to: ", variation)
            await set_light_state(light_id, color_mode, **variation)
            await asyncio.sleep(SLEEP_TIME)
            power = await get_power_usage(power_meter)
            print("Measured power: ", power)
            print()
            row = list(variation.values())
            row.append(power)
            csv_writer.writerow(row)
            if count % 100 == 0:
                csv_file.flush()

        csv_file.close()


async def get_variations(color_mode: str, light: str):
    if color_mode == MODE_HS:
        async for v in get_hs_variations():
            yield v
    elif color_mode == MODE_COLOR_TEMP:
        async for v in get_ct_variations(light):
            yield v
    else:
        async for v in get_brightness_variations():
            yield v


async def get_entity_state(entity_id: str):
    url = HASS_URL + "/states/" + entity_id
    async with aiohttp.ClientSession(headers=auth_header) as session:
        async with session.get(url) as resp:
            response = await resp.json()
            return response


async def get_ct_variations(light: str):
    state = await get_entity_state(light)

    min_mired = state.get("attributes").get("min_mireds")
    max_mired = state.get("attributes").get("max_mireds")

    if max_mired > 500:
        max_mired = 500

    if min_mired < 150:
        min_mired = 150

    for bri in inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 5):
        for mired in inclusive_range(min_mired, max_mired, 10):
            yield {"bri": bri, "ct": mired}


async def get_hs_variations():
    for bri in inclusive_range(START_BRIGHTNESS, MAX_BRIGHTNESS, 10):
        for sat in inclusive_range(1, 255, 10):
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


async def turn_light_on_hs(light: str, bri: int, hue: int, sat: int):
    url = HASS_URL + "/services/light/turn_on"
    async with aiohttp.ClientSession(headers=auth_header) as session:
        await session.post(url, json={'entity_id': light, 'brightness': bri, 'hs_color': [hue/65535*360, sat/255*100]})


async def turn_light_on_ct(light: str, bri: int, ct: int):
    url = HASS_URL + "/services/light/turn_on"
    async with aiohttp.ClientSession(headers=auth_header) as session:
        await session.post(url, json={'entity_id': light, 'brightness': bri, 'color_temp': ct})


async def turn_light_on_bri(light: str, bri: int):
    url = HASS_URL + "/services/light/turn_on"
    async with aiohttp.ClientSession(headers=auth_header) as session:
        await session.post(url, json={'entity_id': light, 'brightness': bri})


async def set_light_state(light: str, color_mode: str, **kwargs):
    if color_mode == MODE_HS:
        await turn_light_on_hs(light, **kwargs)
    elif color_mode == MODE_COLOR_TEMP:
        await turn_light_on_ct(light, **kwargs)
    elif color_mode == MODE_BRIGHTNESS:
        await turn_light_on_bri(light, **kwargs)


async def turn_light_off(light: str):
    url = HASS_URL + "/services/light/turn_off"
    async with aiohttp.ClientSession(headers=auth_header) as session:
        await session.post(url, json={'entity_id': light})


async def get_power_usage(power_meter: str) -> float:
    url = HASS_URL + "/states/" + power_meter
    async with aiohttp.ClientSession(headers=auth_header) as session:
        async with session.get(url) as resp:
            response = await resp.json()
            return response.get("state")


async def measure_standby_usage(light: str, power_meter: str) -> float:
    await turn_light_off(light)
    print("Measuring standby usage. Waiting for 5 seconds...")
    await asyncio.sleep(5)
    return await get_power_usage(power_meter=power_meter)


def get_questions() -> list[dict]:
    return [
        {
            'type': 'list',
            'name': 'color_mode',
            'message': 'Select the color mode?',
            'default': MODE_HS,
            'choices': [MODE_HS, MODE_COLOR_TEMP, MODE_BRIGHTNESS],
        },
        {
            'type': 'confirm',
            'message': 'Do you want to generate model.json?',
            'name': 'generate_model_json',
            'default': True,
        },
        {
            'type': 'input',
            'name': 'light_id',
            'message': 'Specify the full light entity ID'
        },
        {
            'type': 'input',
            'name': 'model_name',
            'message': 'Specify the full light model name',
            'when': lambda answers: answers['generate_model_json']
        },
        {
            'type': 'input',
            'name': 'power_meter',
            'message': 'Specify the full power meter entity ID'
        }
    ]


if __name__ == "__main__":
    asyncio.run(main())
