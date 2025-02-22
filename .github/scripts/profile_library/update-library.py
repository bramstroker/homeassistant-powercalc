from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
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

        mapped_fields = {
            "model": "id",
        }
        skipped_fields = [
            "calculation_enabled_condition",
            "config_flow_discovery_remarks",
            "config_flow_sub_profile_remarks",
            "composite_config",
            "directory",
            "fixed_config",
            "full_path",
            "linear_config",
            "measure_description",
            "playbook_config",
            "sensor_config",
            "sub_profile_select",
        ]
        mapped_dict = {
            mapped_fields.get(key, key): value for key, value in model.items() if key not in skipped_fields
        }
        mapped_dict["hash"] = hashlib.md5(json.dumps(mapped_dict, sort_keys=True).encode()).hexdigest()
        manufacturer["models"].append(mapped_dict)

    json_data = {
        "manufacturers": list(manufacturers.values()),
    }

    with open(
        os.path.join(DATA_DIR, "library.json"),
        "w",
    ) as json_file:
        json_file.write(json.dumps(json_data))

    print("Generated library.json")


def update_authors(model_listing: list[dict]) -> None:
    for model in model_listing:
        author = model.get("author")
        model_json_path = model.get("full_path")
        if author:
            continue

        author = find_first_commit_author(model_json_path)
        if author is None:
            print(f"Skipping {model_json_path}, author not found")
            continue

        write_author_to_file(model_json_path, author)
        print(f"Updated {model_json_path} with author {author}")

def update_translations(model_listing: list[dict]) -> None:
    data_translations: dict[str, str] =  {}
    description_translations: dict[str, str] = {}
    for model in model_listing:
        custom_fields = model.get("fields")
        if not custom_fields:
            continue

        for key, field_data in custom_fields.items():
            data_translations[key] = field_data.get("name")
            description_translations[key] = field_data.get("description")

    if not data_translations:
        print(f"No translations found")
        return

    translation_file = os.path.join(PROJECT_ROOT, "custom_components/powercalc/translations/en.json")
    with open(translation_file) as file:
        json_data = json.load(file)
        step = "library_custom_fields"
        if not step in json_data["config"]["step"]:
            json_data["config"]["step"][step] = {
                "data": {},
                "data_description": {},
            }
        deep_update(json_data["config"]["step"][step]["data"], data_translations)
        deep_update(json_data["config"]["step"][step]["data_description"], description_translations)

    with open(translation_file, "w") as file:
        json.dump(json_data, file, indent=2)


def deep_update(target: dict, updates: dict) -> None:
    """
    Recursively updates a dictionary with another dictionary,
    only adding keys that are missing.
    """
    for key, value in updates.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            deep_update(target[key], value)
        elif key not in target:
            target[key] = value


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
                    "full_path": json_path,
                },
            )
            if "device_type" not in model_data:
                model_data["device_type"] = "light"

            if color_modes:
                model_data["color_modes"] = list(color_modes)
            models.append(model_data)

    return models


def get_color_modes(model_directory: str, data_dir: str, model_data: dict) -> set:
    if "linked_profile" in model_data:
        model_directory = os.path.join(data_dir, model_data["linked_profile"])

    color_modes = set()
    for path in glob.glob(f"{model_directory}/**/*.csv.gz", recursive=True):
        filename = os.path.basename(path)
        index = filename.index(".")
        color_mode = filename[:index]
        color_modes.add(color_mode)
    return color_modes


def get_last_commit_time(directory: str) -> datetime:
    try:
        # Use subprocess to run the git command
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", directory],
            cwd=directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        out = result.stdout.strip()
        if not out:
            return datetime.fromtimestamp(0)
        timestamp = int(out)
        return datetime.fromtimestamp(timestamp)
    except subprocess.CalledProcessError:
        # Handle case where there are no commits or Git command fails
        return datetime.fromtimestamp(0)

def run_git_command(command):
    """Run a git command and return the output."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    result.check_returncode()  # Raise an error if the command fails
    return result.stdout.strip()


def get_commits_affected_directory(directory: str) -> list:
    """Get a list of commits that affected the given directory, including renames."""
    command = f"git log --follow --format='%H' -- '{directory}'"
    commits = run_git_command(command)
    return commits.splitlines()


def get_commit_author(commit_hash: str) -> str:
    """Get the author of a given commit."""
    command = f"git show -s --format='%an <%ae>' {commit_hash}"
    author = run_git_command(command)
    return author


def find_first_commit_author(file: str, check_paths: bool = True) -> str | None:
    """Find the first commit that affected the directory and return the author's name."""
    commits = get_commits_affected_directory(file)
    for commit in reversed(commits):  # Process commits from the oldest to newest
        command = f"git diff-tree --no-commit-id --name-only -r {commit}"
        if not check_paths:
            return get_commit_author(commit)

        affected_files = run_git_command(command)
        file = file.replace(PROJECT_ROOT, "").lstrip("/")
        paths = [file.replace("profile_library", "custom_components/powercalc/data"), file.replace("profile_library", "data"), file]
        if any(path in affected_files.splitlines() for path in paths):
            author = get_commit_author(commit)
            return author
    return None

def read_author_from_file(file_path: str) -> str | None:
    """Read the author from the model.json file."""
    with open(file_path) as file:
        json_data = json.load(file)

    return json_data.get("author")


def write_author_to_file(file_path: str, author: str) -> None:
    """Write the author to the model.json file."""
    # Read the existing content
    with open(file_path) as file:
        json_data = json.load(file)

    json_data["author"] = author

    with open(file_path, "w") as file:
        json.dump(json_data, file, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Process profiles JSON files and perform updates.")
    parser.add_argument("--authors", action="store_true", help="Update authors")
    parser.add_argument("--library-json", action="store_true", help="Generate library.json")
    parser.add_argument("--translations", action="store_true", help="Update translations")
    parser.add_argument("--all", action="store_true", help="Run all operations (default if no arguments)")

    args = parser.parse_args()

    # Determine whether to run all operations
    run_all = not any([args.authors, args.library_json, args.translations]) or args.all

    print("Start reading profiles JSON files..")
    model_list = get_model_list()
    print(f"Found {len(model_list)} profiles")

    if run_all or args.library_json:
        print("Generating library.json..")
        generate_library_json(model_list)

    if run_all or args.authors:
        print("Updating authors..")
        update_authors(model_list)

    if run_all or args.translations:
        print("Updating translations..")
        update_translations(model_list)

if __name__ == "__main__":
    main()
