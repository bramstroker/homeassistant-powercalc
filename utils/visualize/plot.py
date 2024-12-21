#!/usr/bin/env python3

from __future__ import annotations

import argparse
import colorsys
import gzip
import math
import os
from enum import StrEnum
from pathlib import Path

import colour
import matplotlib.pyplot as plt
import numpy as np
import pandas
import pandas as pd


class ColorMode(StrEnum):
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    HS = "hs"


def create_scatter_plot(df: pandas.DataFrame, color_mode: ColorMode) -> None:
    bri = df["bri"]
    watt = df["watt"]
    if color_mode == ColorMode.BRIGHTNESS:
        df["color"] = "#1f77b4"
    elif color_mode == ColorMode.COLOR_TEMP:
        df["color"] = df["mired"].apply(convert_mired_to_rgb)
    else:
        df["color"] = df.apply(
            lambda row: colorsys.hls_to_rgb(
                row.hue / 65535,
                row.bri / 255,
                row.sat / 255,
            ),
            axis=1,
        )

    plt.scatter(bri, watt, color=df["color"], marker=".", s=10)


def mired_to_rgb(mired):
    kelvin = 1000000 / mired
    xy = colour.CCT_to_xy(kelvin, method="Kang 2002")
    xys = colour.xy_to_XYZ(xy)
    rgb = colour.XYZ_to_sRGB(xys)
    # Note that the colours are overflowing 8-bit, thus a normalisation
    # process must be used.
    rgb /= np.max(rgb, axis=1)[..., np.newaxis]
    return rgb


def convert_mired_to_rgb(mired):
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


def create_plot_for_csv_file(file_path: str, output: str) -> None:
    """Create a scatter plot from a CSV file."""
    color_mode = ColorMode(Path(file_path).stem.removesuffix(".csv"))

    if file_path.endswith(".gz"):
        csv_file = gzip.open(file_path, "rt")
    else:
        csv_file = open(file_path, "rt")

    dataframe = pd.read_csv(csv_file)

    plt.figure(figsize=(10, 6))
    create_scatter_plot(dataframe, color_mode)
    plt.xlabel("brightness")
    plt.ylabel("watt")
    if output:
        if output == "auto":
            output = f"{color_mode}.png"
        output_path = Path(output)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path)
        print(f"Save plot to {output}")
        return

    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI script to output powercalc LUT file as a plot",
    )
    parser.add_argument("file")
    parser.add_argument("--output", required=False)
    args = parser.parse_args()

    file_path = resolve_absolute_file_path(args.file)
    create_plot_for_csv_file(file_path, args.output)


def resolve_absolute_file_path(file_path: str) -> str:
    if os.path.exists(file_path):
        return file_path

    library_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../profile_library",
        file_path
    )
    if os.path.exists(library_path):
        return library_path

    raise FileNotFoundError(f"File not found: {file_path}")


if __name__ == "__main__":
    main()
