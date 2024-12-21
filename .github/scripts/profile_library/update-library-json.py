from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import git

sys.path.insert(
    1,
    os.path.abspath(
        os.path.join(Path(__file__), "../../../../custom_components/powercalc"),
    ),
)

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.abspath(__file__), "../../../../"))
DATA_DIR = f"{PROJECT_ROOT}/profile_library"


def generate_library_json(model_listing: list[dict]) -> None:
    manufacturers: dict[str, dict] = {}
    for model in model_listing:
        manufacturer_name = model.get("manufacturer")
        manufacturer = manufacturers.get(manufacturer_name)
        if not manufacturer:
            manufacturer = {
                **get_manufacturer_json(manufacturer_name),
                "models": [],
                "device_types": [],
            }
            manufacturers[manufacturer_name] = manufacturer

        device_type = model.get("device_type")
        if device_type not in manufacturer["device_types"]:
            manufacturer["device_types"].append(device_type)

        key_mapping = {
            "model": "id",
            "name": "name",
            "device_type": "device_type",
            "aliases": "aliases",
            "updated_at": "updated_at",
            "color_modes": "color_modes",
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


def get_manufacturer_json(manufacturer: str) -> dict:
    json_path = os.path.join(DATA_DIR, manufacturer, "manufacturer.json")
    try:
        with open(json_path) as json_file:
            return json.load(json_file)
    except FileNotFoundError:
        default_json = {"name": manufacturer, "aliases": []}
        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(default_json, json_file, ensure_ascii=False, indent=4)
        git.Repo(PROJECT_ROOT).git.add(json_path)
        print(f"Added {json_path}")
        return default_json


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
            updated_at = get_last_commit_time(model_directory).isoformat()
            manufacturer = os.path.basename(os.path.dirname(model_directory))

            model_data.update(
                {
                    "model": os.path.basename(model_directory),
                    "manufacturer": manufacturer,
                    "directory": model_directory,
                    "updated_at": updated_at,
                },
            )
            if "device_type" not in model_data:
                model_data["device_type"] = "light"

            if color_modes:
                model_data["color_modes"] = list(color_modes)
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


def get_last_commit_time(directory: str) -> datetime:
    repo = git.Repo(directory, search_parent_directories=True)
    commits = list(repo.iter_commits(paths=directory))
    if commits:
        last_commit = commits[0]
        return last_commit.committed_datetime
    return datetime.fromtimestamp(0)


model_list = get_model_list()
generate_library_json(model_list)
