from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

from pytablewriter import MarkdownTableWriter

sys.path.insert(
    1,
    os.path.abspath(
        os.path.join(Path(__file__), "../../../../custom_components/powercalc"),
    ),
)

from aliases import MANUFACTURER_DIRECTORY_MAPPING  # noqa: E402

DEVICE_TYPES = [
    ("light", "Lights"),
    ("smart_speaker", "Smart speakers"),
    ("smart_switch", "Smart switches / plugs"),
    ("camera", "Cameras"),
    ("network", "Networking"),
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
            if model.get("device_type") == device_type[0]
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
            "standby",
        ]
        if device_type[0] == "light":
            headers.append("color modes")

        writer.header_list = headers
        rows = []
        for model in relevant_models:
            row = [
                model["manufacturer"],
                model["model"],
                model["name"],
                "<br />".join(model.get("aliases") or []),
                model.get("standby_power") or 0,
            ]
            if device_type[0] == "light":
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
    with open(
        os.path.join(DATA_DIR, "manufacturer_device_types.json"),
        "w",
    ) as json_file:
        json_file.write(json.dumps(manufacturer_device_types))

    print("Generated manufacturer_device_types.json")


def generate_library_json(model_listing: list[dict]) -> None:
    manufacturers: dict[str, dict] = {}
    for model in model_listing:
        manufacturer_name = model.get("manufacturer")
        manufacturer = manufacturers.get(manufacturer_name)
        if not manufacturer:
            manufacturer = {"name": manufacturer_name, "models": [], "device_types": []}
            manufacturers[manufacturer_name] = manufacturer

        device_type = model.get("device_type")
        if device_type not in manufacturer["device_types"]:
            manufacturer["device_types"].append(device_type)

        key_mapping = {
            "model": "id",
            "name": "name",
            "device_type": "device_type",
            "aliases": "aliases",
            "modified": "update_timestamp"
        }

        # Create a new dictionary with updated keys
        mapped_dict = {key_mapping.get(key, key): value for key, value in model.items()}
        manufacturer["models"].append({key: mapped_dict[key] for key in key_mapping.values() if key in mapped_dict})

    json_data = {
        "manufacturers": list(manufacturers.values()),
    }

    with open(
        os.path.join(DATA_DIR, "library.json"),
        "w",
    ) as json_file:
        json_file.write(json.dumps(json_data))

    print("Generated library.json")


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
                    "directory": model_directory,
                    "modified": get_local_modification_time(model_directory),
                },
            )
            if "device_type" not in model_data:
                model_data["device_type"] = "light"
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


def get_local_modification_time(folder: str) -> float:
    """Get the latest modification time of the local profile directory."""
    times = [os.path.getmtime(os.path.join(folder, f)) for f in os.listdir(folder)]
    times.sort(reverse=True)
    return times[0] if times else 0


model_list = get_model_list()
generate_supported_model_list(model_list)
generate_manufacturer_device_types_file(model_list)
generate_library_json(model_list)
