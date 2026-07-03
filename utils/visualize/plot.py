#!/usr/bin/env python3

from __future__ import annotations

import argparse
import colorsys
from enum import StrEnum
import gzip
import json
import math
import os
from pathlib import Path
from typing import TextIO

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


class LutMode(StrEnum):
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    EFFECT = "effect"
    HS = "hs"


def create_color_mode_plot(df: pd.DataFrame, color_mode: LutMode) -> None:
    bri = df["bri"]
    watt = df["watt"]
    if color_mode == LutMode.BRIGHTNESS:
        colors = "#1f77b4"
    elif color_mode == LutMode.COLOR_TEMP:
        colors = df["mired"].apply(convert_mired_to_rgb)
    else:
        colors = df.apply(
            lambda row: colorsys.hls_to_rgb(
                row.hue / 65535,
                row.bri / 255,
                row.sat / 255,
            ),
            axis=1,
        )

    plt.scatter(bri, watt, color=colors, marker=".", s=10)
    plt.xlabel("brightness")


def create_effect_plot(df: pd.DataFrame) -> None:
    sns.lineplot(data=df, x="bri", y="watt", hue="effect", marker="o")
    plt.legend(loc="upper left", bbox_to_anchor=(1.05, 1), borderaxespad=0.0)
    plt.xlabel("brightness")
    plt.tight_layout()


def create_linear_calibration_plot(df: pd.DataFrame) -> None:
    plt.plot(df["volume"], df["watt"], marker="o", linestyle="-")
    plt.xlabel("volume")
    plt.title("Calibration Curve")
    plt.grid(True)


def convert_mired_to_rgb(mired: float) -> list[float]:  # noqa: C901
    """
    Converts from K to RGB, algorithm courtesy of
    http://www.tannerhelland.com/4435/convert-temperature-rgb-algorithm-code/
    """
    colour_temperature = 1000000 / mired

    # range check
    if colour_temperature < 1000:
        colour_temperature = 1000
    elif colour_temperature > 40000:
        colour_temperature = 40000

    tmp_internal = colour_temperature / 100.0

    # red
    if tmp_internal <= 66:
        red = 255
    else:
        tmp_red = 329.698727446 * math.pow(tmp_internal - 60, -0.1332047592)
        if tmp_red < 0:
            red = 0
        elif tmp_red > 255:
            red = 255
        else:
            red = tmp_red

    # green
    if tmp_internal <= 66:
        tmp_green = 99.4708025861 * math.log(tmp_internal) - 161.1195681661
        if tmp_green < 0:
            green = 0
        elif tmp_green > 255:
            green = 255
        else:
            green = tmp_green
    else:
        tmp_green = 288.1221695283 * math.pow(tmp_internal - 60, -0.0755148492)
        if tmp_green < 0:
            green = 0
        elif tmp_green > 255:
            green = 255
        else:
            green = tmp_green

    # blue
    if tmp_internal >= 66:
        blue = 255
    elif tmp_internal <= 19:
        blue = 0
    else:
        tmp_blue = 138.5177312231 * math.log(tmp_internal - 10) - 305.0447927307
        if tmp_blue < 0:
            blue = 0
        elif tmp_blue > 255:
            blue = 255
        else:
            blue = tmp_blue

    rgb = red, green, blue
    return [*[div / 255.0 for div in rgb], 1]


def create_plot(file_path: str, output: str, color_mode: str | None) -> None:
    """Create a scatter plot from a CSV file."""

    is_json_file = file_path.endswith(".json")
    file_name_without_suffix = get_base_filename(file_path)
    if not is_json_file and not color_mode:
        color_mode = LutMode(file_name_without_suffix)

    if is_json_file:
        dataframe = create_dataframe_for_json_file(file_path)
    else:
        csv_file: TextIO
        with gzip.open(file_path, "rt") if file_path.endswith(".gz") else open(file_path) as csv_file:
            dataframe = pd.read_csv(csv_file)

    plt.figure(figsize=(10, 6))
    plt.ylabel("watt")
    if is_json_file:
        create_linear_calibration_plot(dataframe)
    elif color_mode == LutMode.EFFECT:
        create_effect_plot(dataframe)
    else:
        create_color_mode_plot(dataframe, color_mode)

    if output:
        if output == "auto":
            output = f"{file_name_without_suffix}.png"
        output_path = Path(output)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path)
        print(f"Save plot to {output}")  # noqa: T201
        return

    plt.show()


def create_dataframe_for_json_file(file_path: str) -> pd.DataFrame:
    with open(file_path) as json_file:
        json_data = json.load(json_file)
    strategy = json_data.get("calculation_strategy")
    if strategy != "linear":
        raise ValueError(f"Unsupported calculation strategy: {strategy}")
    linear_config = json_data.get("linear_config")
    if "calibrate" not in linear_config:
        raise ValueError("No calibration data found in JSON file")
    calibration_data: list[str] = linear_config.get("calibrate")
    rows = []
    for entry in calibration_data:
        entry_data = entry.split(" -> ")
        if len(entry_data) != 2:
            raise ValueError(f"Invalid calibration entry: {entry}")
        val = int(entry_data[0])
        watt = float(entry_data[1])
        label = "volume"
        rows.append(
            {
                label: val,
                "watt": watt,
            },
        )
    df = pd.DataFrame(rows)
    # Sort by volume to ensure points are plotted in the correct order
    return df.sort_values(by=label)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI script to output powercalc LUT file as a plot",
    )
    parser.add_argument("file")
    parser.add_argument("--output", required=False)
    parser.add_argument("--colormode", required=False)
    args = parser.parse_args()

    file_path = resolve_absolute_file_path(args.file)
    create_plot(file_path, args.output, args.colormode)


def resolve_absolute_file_path(file_path: str) -> str:
    if os.path.exists(file_path):
        return file_path

    library_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../profile_library",
        file_path,
    )
    if os.path.exists(library_path):
        return library_path

    raise FileNotFoundError(f"File not found: {file_path}")


def get_base_filename(path: str | Path) -> str:
    p = Path(path)
    name = p.name
    # Strip multiple known suffixes in order
    for ext in (".gz", ".csv", ".json"):
        name = name.removesuffix(ext)
    return name


if __name__ == "__main__":
    main()
