#!/usr/bin/env python3

import gzip
import os
from collections import namedtuple

import matplotlib.pyplot as plt
import pandas as pd

DataSet = namedtuple("DataSet", ["dataframe", "color", "label"])


def plot_data(df: pd.DataFrame, color: str) -> None:
    x = df["bri"]
    y = df["watt"]
    plt.scatter(x, y, color=color, marker=".", s=10)


def get_library_file(path: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../profile_library/",
        path,
    )


def csv_to_dataframe(csv_file: str) -> pd.DataFrame:
    if csv_file.endswith("gz"):
        csv_file = gzip.open(csv_file, "rt")
    return pd.read_csv(csv_file)


frames = [
    DataSet(csv_to_dataframe("LWA017.csv"), "blue", "1"),
    DataSet(csv_to_dataframe("brightness.csv"), "red", "2"),
]

legend = []
for dataset in frames:
    plot_data(dataset.dataframe, dataset.color)
    legend.append(dataset.label)

plt.show()
