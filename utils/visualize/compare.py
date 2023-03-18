import matplotlib.pyplot as plt
import pandas as pd
import os
import gzip
from collections import namedtuple

DataSet = namedtuple('DataSet', ['dataframe', 'color', 'label'])


def plot_data(df, color):
    x = df["bri"]
    y = df["watt"]
    plt.scatter(x, y, color=color, marker=".", s=10)


def get_library_file(path: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../custom_components/powercalc/data/",
        path
    )


def csv_to_dataframe(
    csv_file: str
) -> pd.DataFrame:
    if csv_file.endswith('gz'):
        csv_file = gzip.open(csv_file, "rt")
    return pd.read_csv(csv_file)


# frames = [
#     DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_1/color_temp.csv.gz')), "blue", "1"),
#     DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_2/color_temp.csv.gz')), "red", "2"),
#     DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_3/color_temp.csv.gz')), "green", "3"),
#     DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_4/color_temp.csv.gz')), "yellow", "4"),
#     DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_5/color_temp.csv.gz')), "purple", "5"),
#     # DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_6/color_temp.csv.gz')), "orange", "6"),
#     # DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_7/color_temp.csv.gz')), "black", "7"),
#     # DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_8/color_temp.csv.gz')), "blue", "8"),
#     # DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_9/color_temp.csv.gz')), "red", "9"),
#     # DataSet(csv_to_dataframe(get_library_file('lifx/LIFX Z/length_10/color_temp.csv.gz')), "green", "10"),
# ]

frames = [
    DataSet(csv_to_dataframe("LWA017.csv"), "blue", "1"),
    DataSet(csv_to_dataframe("brightness.csv"), "red", "2"),
]

legend = []
for dataset in frames:
    plot_data(dataset.dataframe, dataset.color)
    legend.append(dataset.label)

plt.show()
