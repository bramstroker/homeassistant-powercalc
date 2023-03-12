from __future__ import annotations

import argparse
import colorsys
import gzip
import math
import os

import colour
import matplotlib.pyplot as plt
import numpy as np
import pandas
import pandas as pd


def create_scatter_plot(df: pandas.DataFrame, color_mode: str):
    bri = df["bri"]
    watt = df["watt"]
    if color_mode == "brightness":
        df["color"] = "#1f77b4"
    elif color_mode == "color_temp":
        df["color"] = df["mired"].apply(convert_mired_to_rgb)
    else:
        df["color"] = df.apply(
            lambda row: colorsys.hls_to_rgb(
                row.hue / 65535, row.bri / 255, row.sat / 255
            ),
            axis=1,
        )

    plt.scatter(bri, watt, color=df["color"], marker=".", s=10)


def mired_to_rgb(mired):
    kelvin = 1000000 / mired
    xy = colour.CCT_to_xy(kelvin, method="Kang 2002")
    XYZ = colour.xy_to_XYZ(xy)
    RGB = colour.XYZ_to_sRGB(XYZ)
    # Note that the colours are overflowing 8-bit, thus a normalisation
    # process must be used.
    RGB /= np.max(RGB, axis=1)[..., np.newaxis]
    return RGB


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
    return list(map(lambda div: div / 255.0, rgb)) + [1]


def main():
    parser = argparse.ArgumentParser(
        description="CLI script to output powercalc LUT file as a plot"
    )
    parser.add_argument("manufacturer")
    parser.add_argument("model")
    parser.add_argument("color_mode")
    parser.add_argument("--output", required=False)
    args = parser.parse_args()

    data_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../custom_components/powercalc/data",
        args.manufacturer,
        args.model,
    )
    file_path = os.path.join(data_path, f"{args.color_mode}.csv.gz")

    csv_file = gzip.open(file_path, "rt")

    dataframe = pd.read_csv(csv_file)

    plt.figure(figsize=(10, 6))
    create_scatter_plot(dataframe, args.color_mode)
    plt.xlabel("brightness")
    plt.ylabel("watt")
    if args.output:
        plt.savefig(args.output)
    plt.show()


if __name__ == "__main__":
    main()
