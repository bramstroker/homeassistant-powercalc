from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import gzip
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import aiofiles
import git
import httpx
import math

sys.path.insert(
    1,
    os.path.abspath(
        os.path.join(Path(__file__), "../../../../custom_components/powercalc"),
    ),
)

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.abspath(__file__), "../../../../"))
DATA_DIR = f"{PROJECT_ROOT}/profile_library"
REPO_OWNER = "bramstroker"
REPO_NAME = "homeassistant-powercalc"

@dataclass
class Author:
    name: str
    email: str | None
    github_username: str

def create_model_hash(mapping: Mapping) -> str:
    return hashlib.md5(json.dumps(mapping, sort_keys=True).encode()).hexdigest()

async def generate_library_json(model_listing: list[dict]) -> None:
    manufacturers: dict[str, dict] = {}

    # Process manufacturers concurrently
    tasks = []
    for model in model_listing:
        manufacturer_name = model.get("manufacturer")
        if manufacturer_name not in manufacturers:
            task = get_manufacturer_json(manufacturer_name)
            tasks.append((manufacturer_name, task))

    # Wait for all manufacturer data to be fetched
    for manufacturer_name, task in tasks:
        manufacturer_data = await task
        manufacturers[manufacturer_name] = {
            **manufacturer_data,
            "models": [],
            "device_types": [],
        }

    # Process models
    for model in model_listing:
        manufacturer_name = model.get("manufacturer")
        manufacturer = manufacturers.get(manufacturer_name)

        device_type = model.get("device_type")
        if device_type not in manufacturer["device_types"]:
            manufacturer["device_types"].append(device_type)

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
            key: value for key, value in model.items() if key not in skipped_fields
        }
        hash_dict = {key: value for key, value in mapped_dict.items() if key != "sub_profile_count"}
        mapped_dict["hash"] = create_model_hash(hash_dict)
        manufacturer["models"].append(mapped_dict)

    json_data = {
        "manufacturers": list(manufacturers.values()),
    }

    async with aiofiles.open(
        os.path.join(DATA_DIR, "library.json"),
        "w",
    ) as json_file:
        await json_file.write(json.dumps(json_data))

    print("Generated library.json")


async def update_authors(model_listing: list[dict]) -> None:
    tasks = []
    for model in model_listing:
        author = model.get("author_info")
        model_json_path = model.get("full_path")
        if author:
            continue

        tasks.append(process_author_update(model_json_path))

    if tasks:
        await asyncio.gather(*tasks)

async def process_author_update(model_json_path: str) -> None:
    """Process a single author update asynchronously"""
    author = await find_first_commit_author(model_json_path)
    if author is None:
        print(f"Skipping {model_json_path}, author not found")
        return

    await write_author_to_file(model_json_path, author)
    print(f"Updated {model_json_path} with author {author}")

async def update_translations(model_listing: list[dict]) -> None:
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
    async with aiofiles.open(translation_file, mode='r') as file:
        content = await file.read()
        json_data = json.loads(content)
        step = "library_custom_fields"
        if not step in json_data["config"]["step"]:
            json_data["config"]["step"][step] = {
                "data": {},
                "data_description": {},
            }
        deep_update(json_data["config"]["step"][step]["data"], data_translations)
        deep_update(json_data["config"]["step"][step]["data_description"], description_translations)

    async with aiofiles.open(translation_file, mode='w') as file:
        await file.write(json.dumps(json_data, indent=2))


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


async def get_manufacturer_json(manufacturer: str) -> dict:
    json_path = os.path.join(DATA_DIR, manufacturer, "manufacturer.json")
    try:
        async with aiofiles.open(json_path, mode='r') as json_file:
            content = await json_file.read()
            manufacturer_data = json.loads(content)
            return {
                "aliases": manufacturer_data.get("aliases", []),
                "name": manufacturer,
                "full_name": manufacturer_data.get("name"),
                "dir_name": manufacturer
            }
    except FileNotFoundError:
        default_json = {
            "name": manufacturer.capitalize(),
            "aliases": []
        }
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        async with aiofiles.open(json_path, mode='w', encoding="utf-8") as json_file:
            await json_file.write(json.dumps(default_json, ensure_ascii=False, indent=4))
        git.Repo(PROJECT_ROOT).git.add(json_path)
        print(f"Added {json_path}")
        return default_json


async def get_model_list() -> list[dict]:
    """Get a listing of all available powercalc models"""
    json_paths = glob.glob(
        f"{DATA_DIR}/*/*/model.json",
        recursive=True,
    )

    # Process files concurrently
    tasks = [process_model_file(json_path) for json_path in json_paths]
    models = await asyncio.gather(*tasks)

    # Filter out None values (if any)
    return [model for model in models if model]

async def process_model_file(json_path: str) -> dict:
    """Process a single model file asynchronously"""
    async with aiofiles.open(json_path, mode='r') as json_file:
        content = await json_file.read()
        model_data: dict = json.loads(content)
        model_directory = os.path.dirname(json_path)
        model_data['id'] = os.path.basename(model_directory)
        if "linked_profile" in model_data:
            model_directory = os.path.join(DATA_DIR, model_data["linked_profile"])

        # Get these values concurrently
        updated_at, max_power, sub_profile_count, color_modes = await asyncio.gather(
            get_last_commit_time(model_directory),
            get_max_power(model_directory, model_data),
            get_sub_profile_count(model_directory),
            get_color_modes(model_directory)
        )

        model_data.update(
            {
                "manufacturer": os.path.basename(os.path.dirname(model_directory)),
                "directory": model_directory,
                "updated_at": updated_at.isoformat(),
                "full_path": json_path,
                "max_power": max_power,
                "sub_profile_count": sub_profile_count,
            },
        )
        if "device_type" not in model_data:
            model_data["device_type"] = "light"

        if color_modes:
            model_data["color_modes"] = list(color_modes)

        return model_data


async def get_color_modes(model_directory: str) -> set:
    color_modes = set()
    paths = glob.glob(f"{model_directory}/**/*.csv.gz", recursive=True)
    for path in paths:
        filename = os.path.basename(path)
        try:
            index = filename.index(".")
            color_mode = filename[:index]
            color_modes.add(color_mode)
        except ValueError:
            continue
    return color_modes


async def get_sub_profile_count(model_directory: str) -> int:
    path = Path(model_directory)
    return sum(1 for p in path.iterdir() if p.is_dir())

async def get_max_power(model_directory: str, model_data: dict) -> float | None:
    calculation_strategy = model_data.get("calculation_strategy", "lut")
    if calculation_strategy == "lut":
        max_power = 0
        paths = glob.glob(f"{model_directory}/**/*.csv.gz", recursive=True)

        # Process CSV files concurrently
        if paths:
            tasks = [process_csv_file(path) for path in paths]
            power_values = await asyncio.gather(*tasks)
            # Filter out None values and find max
            valid_powers = [p for p in power_values if p is not None]
            if valid_powers:
                return max(valid_powers)
            return max_power
        return max_power

    if calculation_strategy == "linear":
        linear_config = model_data.get("linear_config", {})
        if "calibrate" in linear_config:
            power_values = [float(line.split("->")[1].strip()) for line in linear_config.get("calibrate", []) if "->" in line]
            return max(power_values) if power_values else 0
        return max(linear_config.get("max_power", 0), model_data.get("standby_power_on", 0))

    if calculation_strategy == "fixed":
        fixed_config = model_data.get("fixed_config", {})
        power_values = [
            fixed_config.get("power", 0),
            model_data.get("standby_power_on", 0),
        ]
        states_power = fixed_config.get("states_power", {})
        power_values.extend(states_power.values())
        power_values = filter(lambda p: is_number(p), power_values)

        return max(power_values) if power_values else 0

    return None

async def process_csv_file(path: str) -> float | None:
    """Process a single CSV file to find the maximum power value"""
    try:
        with gzip.open(path, 'rt') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header row
            max_power = 0
            for row in reader:
                if not row:
                    continue
                try:
                    watt = float(row[-1])
                    if watt > max_power:
                        max_power = watt
                except (ValueError, IndexError):
                    continue
            return max_power if max_power > 0 else None
    except Exception as e:
        print(f"Error processing {path}: {e}")
        return None


async def get_last_commit_time(directory: str) -> datetime:
    try:
        # Use asyncio to run the git command
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "-1", "--format=%ct", "--", directory,
            cwd=directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return datetime.fromtimestamp(0)

        out = stdout.decode().strip()
        if not out:
            return datetime.fromtimestamp(0)
        timestamp = int(out)
        return datetime.fromtimestamp(timestamp)
    except (asyncio.SubprocessError, ValueError):
        # Handle case where there are no commits or Git command fails
        return datetime.fromtimestamp(0)

async def run_git_command(command):
    """Run a git command asynchronously and return the output."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise asyncio.SubprocessError(f"Command failed: {command}, error: {stderr.decode()}")

    return stdout.decode().strip()


async def get_commits_affected_directory(directory: str) -> list:
    """Get a list of commits that affected the given directory, including renames."""
    command = f"git log --follow --format='%H' -- '{directory}'"
    commits = await run_git_command(command)
    return commits.splitlines()


async def get_commit_author(commit_hash: str) -> Author | None:
    """Get the author of a given commit."""
    headers = {}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{commit_hash}",
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()

    if not "commit" in data and not "author" in data:
        return None

    commit = data.get("commit")
    author = data.get("author")

    email = commit["author"]["email"]
    if email.endswith("@users.noreply.github.com"):
        email = None
    return Author(
        name=commit["author"]["name"].replace("@", ""),
        email=email,
        github_username=author["login"] if author else None,
    )

async def find_first_commit_author(file: str, check_paths: bool = True) -> Author | None:
    """Find the first commit that affected the directory and return the author's name."""
    commits = await get_commits_affected_directory(file)
    for commit in reversed(commits):  # Process commits from the oldest to newest
        command = f"git diff-tree --no-commit-id --name-only -r {commit}"
        if not check_paths:
            return await get_commit_author(commit)

        affected_files = await run_git_command(command)
        file = file.replace(PROJECT_ROOT, "").lstrip("/")
        paths = [file.replace("profile_library", "custom_components/powercalc/data"), file.replace("profile_library", "data"), file]
        if any(path in affected_files.splitlines() for path in paths):
            author = await get_commit_author(commit)
            return author
    return None

async def read_author_from_file(file_path: str) -> str | None:
    """Read the author from the model.json file."""
    async with aiofiles.open(file_path, mode='r') as file:
        content = await file.read()
        json_data = json.loads(content)

    return json_data.get("author")


async def write_author_to_file(file_path: str, author: Author) -> None:
    """Write the author to the model.json file."""
    # Read the existing content
    async with aiofiles.open(file_path, mode='r') as file:
        content = await file.read()
        json_data = json.loads(content)

    json_data["author_info"] = {
        "name": author.name,
        "email": author.email,
        "github": author.github_username,
    }

    async with aiofiles.open(file_path, mode='w') as file:
        await file.write(json.dumps(json_data, indent=2))

async def main_async():
    parser = argparse.ArgumentParser(description="Process profiles JSON files and perform updates.")
    parser.add_argument("--authors", action="store_true", help="Update authors")
    parser.add_argument("--library-json", action="store_true", help="Generate library.json")
    parser.add_argument("--translations", action="store_true", help="Update translations")
    parser.add_argument("--all", action="store_true", help="Run all operations (default if no arguments)")

    args = parser.parse_args()

    # Determine whether to run all operations
    run_all = not any([args.authors, args.library_json, args.translations]) or args.all

    print("Start reading profiles JSON files..")
    start_time = datetime.now()
    model_list = await get_model_list()
    print(f"Found {len(model_list)} profiles in {(datetime.now() - start_time).total_seconds():.2f} seconds")

    tasks = []

    if run_all or args.library_json:
        print("Generating library.json..")
        tasks.append(generate_library_json(model_list))

    if run_all or args.authors:
        print("Updating authors..")
        tasks.append(update_authors(model_list))

    if run_all or args.translations:
        print("Updating translations..")
        tasks.append(update_translations(model_list))

    # Run all tasks concurrently
    if tasks:
        await asyncio.gather(*tasks)

    total_time = (datetime.now() - start_time).total_seconds()
    print(f"All operations completed in {total_time:.2f} seconds")

def is_number(value):
    """Try to convert value to a float."""
    try:
        fvalue = float(value)
    except (ValueError, TypeError):
        return False
    if not math.isfinite(fvalue):
        return False
    return True

def main():
    """Entry point that runs the async main function"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
