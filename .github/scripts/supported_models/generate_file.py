from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(
    1,
    os.path.abspath(
        os.path.join(Path(__file__), "../../../../custom_components/powercalc")
    ),
)

from aliases import MANUFACTURER_DIRECTORY_MAPPING
from pytablewriter import MarkdownTableWriter

DEVICE_TYPES = [
    ("light", "Lights"),
    ("smart_speaker", "Smart speakers"),
    ("smart_switch", "Smart switches"),
]

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.abspath(__file__), "../../../../"))
DATA_DIR = f"{PROJECT_ROOT}/custom_components/powercalc/data"


def generate_supported_model_list(model_listing: list[dict]):
    """Generate static file containing the supported models."""
    toc_links: list[str] = []
    tables_output: str = ""

    for device_type in DEVICE_TYPES:
        relevant_models = [
            model
            for model in model_listing
            if (model.get("device_type") or "light") == device_type[0]
        ]
        num_devices = len(relevant_models)

        anchor = device_type[1].replace(" ", "-")
        toc_links.append(f"- [{device_type[1]}](#{anchor}) ({num_devices})\n")

        writer = MarkdownTableWriter()
        headers = [
            "manufacturer",
            "model id",
            "name",
            "aliases",
        ]
        if device_type == "light":
            headers.append("color modes")

        writer.header_list = headers
        rows = []
        for model in relevant_models:
            row = [
                model["manufacturer"],
                model["model"],
                model["name"],
                ",".join(model.get("aliases") or []),
            ]
            if device_type == "light":
                row.append(",".join(model.get("color_modes") or []))
            rows.append(row)

        rows = sorted(rows, key=lambda x: (x[0], x[1]))
        writer.value_matrix = rows
        tables_output += f"\n## {device_type[1]}\n#### {num_devices} total\n\n"
        tables_output += writer.dumps()

    md_file = open(os.path.join(PROJECT_ROOT, "docs/supported_models.md"), "w")
    md_file.write("".join(toc_links) + tables_output)
    md_file.close()

    print("Generated supported_models.md")


def generate_manufacturer_device_types_file(model_listing: list[dict]) -> None:
    manufacturer_device_types: dict[str, list] = {}
    for model in model_listing:
        device_type = model.get("device_type") or "light"
        manufacturer = model.get("manufacturer")
        if manufacturer not in manufacturer_device_types:
            manufacturer_device_types[manufacturer] = []
        if device_type not in manufacturer_device_types[manufacturer]:
            manufacturer_device_types[manufacturer].append(device_type)
    with open(os.path.join(DATA_DIR, "manufacturer_device_types.json"), "w") as json_file:
        json_file.write(json.dumps(manufacturer_device_types))

    print("Generated manufacturer_device_types.json")


def get_model_list() -> list[dict]:
    """Get a listing of all available powercalc models"""
    models = []
    for json_path in glob.glob(
        f"{DATA_DIR}/*/*/model.json",
        recursive=True,
    ):
        with open(json_path) as json_file:
            model_directory = os.path.dirname(json_path)
            model_data: dict = json.load(json_file)
            color_modes = get_color_modes(model_directory, DATA_DIR, model_data)
            model_data.update(
                {
                    "model": os.path.basename(model_directory),
                    "manufacturer": os.path.basename(os.path.dirname(model_directory)),
                    "color_modes": color_modes,
                }
            )
            models.append(model_data)

    return models


def get_color_modes(model_directory: str, data_dir: str, model_data: dict) -> set:
    if "linked_lut" in model_data:
        model_directory = os.path.join(data_dir, model_data["linked_lut"])

    color_modes = set()
    for path in glob.glob(f"{model_directory}/**/*.csv.gz", recursive=True):
        filename = os.path.basename(path)
        index = filename.index(".")
        color_mode = filename[:index]
        color_modes.add(color_mode)
    return color_modes


def get_manufacturer_by_directory_name(search_directory: str) -> str | None:
    for manufacturer, directory in MANUFACTURER_DIRECTORY_MAPPING.items():
        if search_directory == directory:
            return manufacturer

    return None


model_list = get_model_list()
generate_supported_model_list(model_list)
generate_manufacturer_device_types_file(model_list)
