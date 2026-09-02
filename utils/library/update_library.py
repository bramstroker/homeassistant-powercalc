from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
import csv
from dataclasses import dataclass
from datetime import datetime
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any

import aiofiles
import git
import httpx

from utils.library.common import PROFILE_DIRECTORY, open_lut_file
from utils.library.scan_lut_quality import score_profile_directory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = str(Path(PROFILE_DIRECTORY).resolve())  # resolve, PROFILE_DIRECTORY contains ../.. segments
REPO_OWNER = "bramstroker"
REPO_NAME = "homeassistant-powercalc"
MAX_CONCURRENT_FILE_TASKS = 50
VOLTAGE_RANGE = "voltage_range"
LEGACY_MIN_VOLTAGE = "min_voltage"
LEGACY_MAX_VOLTAGE = "max_voltage"
DISCOVERY_LOW_PRIORITY_DOMAINS: list[str] = [
    "androidtv",
    "dlna_dmr",
    "mikrotik",
    "netgear",
    "onvif",
    "unifi",
    "wake_on_lan",
]


@dataclass
class Author:
    name: str
    email: str | None
    github_username: str


def migrate_voltage_range(model: dict[str, Any]) -> None:
    """Fold the deprecated min_voltage/max_voltage fields into voltage_range.

    Profiles contributed before voltage_range existed still carry the old fields, so the
    library index exposes a single shape to consumers regardless of when a profile was written.
    """
    min_voltage = model.pop(LEGACY_MIN_VOLTAGE, None)
    max_voltage = model.pop(LEGACY_MAX_VOLTAGE, None)
    if VOLTAGE_RANGE in model or min_voltage is None or max_voltage is None:
        return
    model[VOLTAGE_RANGE] = {"min": min_voltage, "max": max_voltage}


def create_model_hash(mapping: Mapping[str, object]) -> str:
    return hashlib.md5(json.dumps(mapping, sort_keys=True).encode(), usedforsecurity=False).hexdigest()


async def generate_library_json(model_listing: list[dict[str, Any]]) -> None:
    manufacturers: dict[str, dict[str, Any]] = {}
    model_listing = sorted(
        model_listing,
        key=lambda model: (model["manufacturer"].casefold(), model["id"].casefold()),
    )

    # Process manufacturers concurrently
    tasks = []
    for model in model_listing:
        manufacturer_name = model["manufacturer"]
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
        manufacturer = manufacturers[model["manufacturer"]]

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
            "playbook_config",
            "sensor_config",
            "sub_profile_select",
        ]
        mapped_dict = {key: value for key, value in model.items() if key not in skipped_fields}
        migrate_voltage_range(mapped_dict)
        # Derived metadata only, not profile content. The hash decides whether a Home Assistant
        # install re-downloads a profile, so folding these in would make every install re-fetch
        # every profile it uses whenever the scoring changes.
        unhashed_fields = ("sub_profile_count", "lut_quality", "power_range", "measurement_updated_at")
        hash_dict = {key: value for key, value in mapped_dict.items() if key not in unhashed_fields}
        mapped_dict["hash"] = create_model_hash(hash_dict)
        manufacturer["models"].append(mapped_dict)

    json_data = {
        "discovery_low_priority_domains": DISCOVERY_LOW_PRIORITY_DOMAINS,
        "manufacturers": list(manufacturers.values()),
    }

    async with aiofiles.open(
        os.path.join(DATA_DIR, "library.json"),
        "w",
    ) as json_file:
        await json_file.write(json.dumps(json_data, indent=2) + "\n")

    print("Generated library.json")


async def update_authors(_model_listing: list[dict[str, Any]]) -> None:
    model_json_paths = sorted(
        glob.glob(f"{DATA_DIR}/**/model.json", recursive=True),
        key=lambda model_json_path: (len(Path(model_json_path).parts), model_json_path),
    )
    for model_json_path in model_json_paths:
        await process_author_update(model_json_path)


async def process_author_update(model_json_path: str) -> None:
    """Process a single author update asynchronously"""
    async with aiofiles.open(model_json_path) as file:
        content = await file.read()
        json_data = json.loads(content)

    changed = False
    if "author_info" in json_data:
        legacy_author = json_data.pop("author_info")
        if "authors" not in json_data and isinstance(legacy_author, dict):
            json_data["authors"] = [legacy_author]
        changed = True

    if is_main_model_json(model_json_path) and not has_authors(json_data):
        author = await find_first_commit_author(model_json_path)
        if author is None:
            print(f"Skipping {model_json_path}, author not found")
        else:
            json_data["authors"] = [author_to_json(author)]
            changed = True

    if "author" in json_data:
        del json_data["author"]
        changed = True

    if not changed:
        return

    async with aiofiles.open(model_json_path, mode="w") as file:
        await file.write(json.dumps(json_data, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated author metadata in {model_json_path}")


def has_authors(model_data: dict[str, Any]) -> bool:
    authors = model_data.get("authors")
    return (
        isinstance(authors, list)
        and bool(authors)
        and all(
            isinstance(author, dict) and bool(author.get("name")) and bool(author.get("github")) for author in authors
        )
    )


def is_main_model_json(model_json_path: str) -> bool:
    relative_path = Path(model_json_path).relative_to(DATA_DIR)
    return len(relative_path.parts) == 3


def author_to_json(author: Author) -> dict[str, str]:
    author_json = {
        "name": author.name,
        "github": author.github_username,
    }
    if author.email:
        author_json["email"] = author.email
    return author_json


async def update_translations(model_listing: list[dict[str, Any]]) -> None:
    data_translations: dict[str, str] = {}
    description_translations: dict[str, str] = {}
    for model in model_listing:
        custom_fields = model.get("fields")
        if not custom_fields:
            continue

        for key, field_data in custom_fields.items():
            data_translations[key] = field_data.get("name")
            description_translations[key] = field_data.get("description")

    if not data_translations:
        print("No translations found")
        return

    translation_file = PROJECT_ROOT / "custom_components/powercalc/translations/en.json"
    async with aiofiles.open(translation_file) as file:
        content = await file.read()
        json_data = json.loads(content)
        step = "library_custom_fields"
        if step not in json_data["config"]["step"]:
            json_data["config"]["step"][step] = {
                "data": {},
                "data_description": {},
            }
        deep_update(json_data["config"]["step"][step]["data"], data_translations)
        deep_update(json_data["config"]["step"][step]["data_description"], description_translations)

    async with aiofiles.open(translation_file, mode="w") as file:
        await file.write(json.dumps(json_data, indent=2) + "\n")


def deep_update(target: dict[str, Any], updates: dict[str, Any]) -> None:
    """
    Recursively updates a dictionary with another dictionary,
    only adding keys that are missing.
    """
    for key, value in updates.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            deep_update(target[key], value)
        elif key not in target:
            target[key] = value


async def get_manufacturer_json(manufacturer: str) -> dict[str, Any]:
    json_path = os.path.join(DATA_DIR, manufacturer, "manufacturer.json")
    try:
        async with aiofiles.open(json_path) as json_file:
            content = await json_file.read()
            manufacturer_data = json.loads(content)
    except FileNotFoundError:
        # A manufacturer added without its own manufacturer.json. Seed one from the directory
        # name, then describe it exactly as an existing one, so the entry written to the library
        # this run carries every field consumers rely on instead of only the seeded ones.
        manufacturer_data = {"name": manufacturer.capitalize(), "aliases": []}
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        async with aiofiles.open(json_path, mode="w", encoding="utf-8") as json_file:
            await json_file.write(json.dumps(manufacturer_data, ensure_ascii=False, indent=4) + "\n")
        git.Repo(PROJECT_ROOT).git.add(json_path)
        print(f"Added {json_path}")

    entry = {
        "aliases": manufacturer_data.get("aliases", []),
        "name": manufacturer,
        "full_name": manufacturer_data.get("name"),
        "dir_name": manufacturer,
    }

    # Brand details, for consumers presenting the manufacturer rather than matching on it.
    # Left out entirely when a manufacturer.json does not carry them.
    for key in ("website", "country", "description"):
        value = manufacturer_data.get(key)
        if value:
            entry[key] = value

    return entry


async def get_model_list() -> list[dict[str, Any]]:
    """Get a listing of all available powercalc models"""
    json_paths = glob.glob(
        f"{DATA_DIR}/*/*/model.json",
        recursive=True,
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILE_TASKS)

    async def process_with_limit(json_path: str) -> dict[str, Any]:
        async with semaphore:
            return await process_model_file(json_path)

    models = await asyncio.gather(*(process_with_limit(json_path) for json_path in json_paths))

    # Filter out None values (if any)
    return [model for model in models if model]


async def process_model_file(json_path: str) -> dict[str, Any]:
    """Process a single model file asynchronously"""
    async with aiofiles.open(json_path) as json_file:
        content = await json_file.read()
        model_data: dict[str, Any] = json.loads(content)
        model_data.pop("author", None)
        model_directory = os.path.dirname(json_path)
        model_data["id"] = os.path.basename(model_directory)
        if "linked_profile" in model_data:
            model_directory = os.path.join(DATA_DIR, model_data["linked_profile"])

        # Get these values concurrently
        (
            updated_at,
            measurement_updated_at,
            power_values,
            sub_profile_count,
            color_modes,
            lut_quality,
        ) = await asyncio.gather(
            get_last_commit_time(model_directory),
            get_last_measurement_commit_time(model_directory),
            get_power_values(model_directory, model_data),
            asyncio.to_thread(get_sub_profile_count, model_directory),
            get_color_modes(model_directory),
            asyncio.to_thread(get_lut_quality, model_directory),
        )
        min_power, max_power, standby_power = power_values

        model_data.update(
            {
                "manufacturer": os.path.basename(os.path.dirname(model_directory)),
                "directory": model_directory,
                "updated_at": updated_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "full_path": json_path,
                "max_power": max_power,
                "sub_profile_count": sub_profile_count,
            },
        )
        if measurement_updated_at is not None:
            model_data["measurement_updated_at"] = measurement_updated_at.isoformat(timespec="seconds").replace(
                "+00:00",
                "Z",
            )

        # Both ends of the curve, so consumers can show the span a device actually draws.
        # `max_power` stays as it is: it predates this and is part of the profile hash.
        if min_power is not None and max_power is not None:
            model_data["power_range"] = {"min": min_power, "max": max_power}

        if standby_power is not None:
            model_data["standby_power"] = standby_power
        if "device_type" not in model_data:
            model_data["device_type"] = "light"

        if color_modes:
            model_data["color_modes"] = sorted(color_modes)

        if lut_quality:
            model_data["lut_quality"] = lut_quality

        return model_data


def get_lut_quality(model_directory: str) -> dict[str, float]:
    """Score the LUT files of a profile, leaving the score off when they cannot be read.

    A malformed CSV is already caught by the validate-lut-files workflow. Should one slip
    through anyway, only that profile loses its score rather than the whole library index
    failing to regenerate over a cosmetic field.
    """
    try:
        return score_profile_directory(Path(model_directory))
    except (ValueError, OSError, EOFError, UnicodeDecodeError, csv.Error) as error:
        print(f"Error scoring LUT quality for {model_directory}: {error}")
        return {}


async def get_color_modes(model_directory: str) -> set[str]:
    """Return the supported light color modes from known LUT file names only."""
    return await asyncio.to_thread(_get_color_modes, model_directory)


def _get_color_modes(model_directory: str) -> set[str]:
    """Find known light color modes without blocking the event loop."""
    from utils.library.validate_lut_files import get_color_mode

    return {
        color_mode for path in Path(model_directory).rglob("*.csv*") if (color_mode := get_color_mode(path)) is not None
    }


def get_sub_profile_count(model_directory: str) -> int:
    path = Path(model_directory)
    return sum(1 for p in path.iterdir() if p.is_dir())


async def get_power_values(
    model_directory: str,
    model_data: dict[str, Any],
) -> tuple[float | None, float | None, float | None]:
    """Return the lowest and highest power, and the highest standby power, over all effective profiles."""
    profiles = await asyncio.to_thread(get_effective_profiles, model_directory, model_data)

    power_ranges = await asyncio.gather(
        *(get_power_range(profile_directory, profile_data) for profile_directory, profile_data in profiles),
    )
    valid_min_powers = [minimum for minimum, _maximum in power_ranges if minimum is not None]
    valid_max_powers = [maximum for _minimum, maximum in power_ranges if maximum is not None]
    standby_powers = [
        float(profile_data["standby_power"])
        for _profile_directory, profile_data in profiles
        if is_number(profile_data.get("standby_power"))
    ]

    return (
        min(valid_min_powers) if valid_min_powers else None,
        max(valid_max_powers) if valid_max_powers else None,
        max(standby_powers) if standby_powers else None,
    )


def get_effective_profiles(
    model_directory: str,
    model_data: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Load the effective configuration of the base profile and its sub-profiles."""
    profiles = [(model_directory, model_data)]
    for sub_profile_directory in (path for path in Path(model_directory).iterdir() if path.is_dir()):
        sub_profile_data: dict[str, Any] = {}
        sub_profile_json = sub_profile_directory / "model.json"
        if sub_profile_json.is_file():
            sub_profile_data = json.loads(sub_profile_json.read_text())

        profiles.append((str(sub_profile_directory), {**model_data, **sub_profile_data}))

    return profiles


async def get_power_range(model_directory: str, model_data: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return the lowest and highest power a single profile draws, as far as its strategy knows it.

    The maximum is what the library has always published as `max_power`, so its value per
    strategy must not shift. The minimum is the other end of the same data: the dimmest row of
    the LUT, the lowest calibration point, the cheapest state of a fixed profile.
    """
    calculation_strategy = model_data.get("calculation_strategy", "lut")
    if calculation_strategy == "lut":
        max_power = 0
        paths = glob.glob(f"{model_directory}/**/*.csv.gz", recursive=True)

        # Process CSV files concurrently
        if paths:
            tasks = [process_csv_file(path) for path in paths]
            csv_powers = await asyncio.gather(*tasks)
            # Filter out None values and find the outer bounds
            valid_powers = [power_range for power_range in csv_powers if power_range is not None]
            if valid_powers:
                return min(minimum for minimum, _maximum in valid_powers), max(
                    maximum for _minimum, maximum in valid_powers
                )
            return None, max_power
        return None, max_power

    if calculation_strategy == "linear":
        linear_config = model_data.get("linear_config", {})
        if "calibrate" in linear_config:
            calibrate_powers = [
                float(line.split("->")[1].strip()) for line in linear_config.get("calibrate", []) if "->" in line
            ]
            if calibrate_powers:
                return min(calibrate_powers), max(calibrate_powers)
            return None, 0
        min_power = linear_config.get("min_power")
        return (
            float(min_power) if is_number(min_power) else None,
            float(max(linear_config.get("max_power", 0), model_data.get("standby_power_on", 0))),
        )

    if calculation_strategy == "fixed":
        fixed_config = model_data.get("fixed_config", {})
        candidates = [
            fixed_config.get("power", 0),
            model_data.get("standby_power_on", 0),
            *fixed_config.get("states_power", {}).values(),
        ]
        fixed_powers = [float(value) for value in candidates if is_number(value)]
        # The zeros above stand in for values the profile does not set. They cannot pull the
        # maximum down, but they would happily claim to be the low end of the range.
        declared_powers = [power for power in fixed_powers if power > 0]

        if declared_powers:
            standby_power = model_data.get("standby_power")
            standby_power_value = float(standby_power) if standby_power is not None and is_number(standby_power) else 0
            if standby_power_value > 0:
                declared_powers.append(standby_power_value)
            return min(declared_powers), max(fixed_powers)
        return None, max(fixed_powers) if fixed_powers else 0

    return None, None


async def process_csv_file(path: str) -> tuple[float, float] | None:
    """Process a single CSV file to find the lowest and highest power value"""
    try:
        with open_lut_file(Path(path)) as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header row
            min_power = None
            max_power = 0.0
            for row in reader:
                if not row:
                    continue
                try:
                    watt = float(row[-1])
                    if watt > max_power:
                        max_power = watt
                    if min_power is None or watt < min_power:
                        min_power = watt
                except ValueError, IndexError:
                    continue
            if max_power > 0 and min_power is not None:
                return min_power, max_power
            return None
    except (OSError, EOFError, UnicodeDecodeError, csv.Error) as e:
        print(f"Error processing {path}: {e}")
        return None


async def get_last_measurement_commit_time(directory: str) -> datetime | None:
    """Return when the measurement data of a profile last changed, None when it has none.

    `updated_at` moves for any commit touching the directory, a typo fix in model.json
    included, which makes it a poor answer to "when was this device last measured?". This
    looks at the LUT files alone. Profiles that carry no CSV files keep the field off rather
    than reporting their metadata date as a measurement date.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "-1",
            "--format=%ct",
            "--",
            "*.csv.gz",
            "*.csv",
            cwd=directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()

        if proc.returncode != 0:
            return None

        out = stdout.decode().strip()
        if not out:
            return None

        return datetime.fromtimestamp(int(out))
    except subprocess.SubprocessError, ValueError, OSError:
        return None


async def get_last_commit_time(directory: str) -> datetime:
    try:
        # Use asyncio to run the git command
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "-1",
            "--format=%ct",
            "--",
            directory,
            cwd=directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()

        if proc.returncode != 0:
            return datetime.fromtimestamp(0)

        out = stdout.decode().strip()
        if not out:
            return datetime.fromtimestamp(0)
        timestamp = int(out)
        return datetime.fromtimestamp(timestamp)
    except subprocess.SubprocessError, ValueError:
        # Handle case where there are no commits or Git command fails
        return datetime.fromtimestamp(0)


async def run_git_command(command: list[str]) -> str:
    """Run a git command asynchronously and return the output.

    The command is passed as an argument list and executed without a shell, so profile
    directory names reach git as literal arguments rather than as shell syntax.
    """
    proc = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise subprocess.SubprocessError(f"Command failed: {shlex.join(command)}, error: {stderr.decode()}")

    return stdout.decode().strip()


async def get_commits_affected_directory(directory: str) -> list[str]:
    """Get a list of commits that affected the given directory, including renames."""
    commits = await run_git_command(["git", "log", "--follow", "--format=%H", "--", directory])
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

        if "commit" not in data and "author" not in data:
            return None

        commit = data.get("commit")
        author = data.get("author")

        github_username = author["login"] if author else None
        if not github_username:
            # Commit email is not linked to a GitHub account, fall back to the author of the associated pull request
            github_username = await get_pull_request_author(client, commit_hash, headers)
        if not github_username:
            # Skip rather than writing a null github field, which violates the model schema
            return None

    email = commit["author"]["email"]
    if email.endswith("@users.noreply.github.com"):
        email = None
    return Author(
        name=commit["author"]["name"].replace("@", ""),
        email=email,
        github_username=github_username,
    )


async def get_pull_request_author(client: httpx.AsyncClient, commit_hash: str, headers: dict[str, str]) -> str | None:
    """Get the author of the pull request that contains the given commit."""
    r = await client.get(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{commit_hash}/pulls",
        headers=headers,
    )
    r.raise_for_status()
    pulls = r.json()
    if not pulls:
        return None
    user = pulls[0].get("user")
    return user.get("login") if user else None


async def find_first_commit_author(file: str, check_paths: bool = True) -> Author | None:
    """Find the first commit that affected the directory and return the author's name."""
    commits = await get_commits_affected_directory(file)
    relative_file = str(Path(file).relative_to(PROJECT_ROOT))
    for commit in reversed(commits):  # Process commits from the oldest to newest
        command = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit]
        if not check_paths:
            return await get_commit_author(commit)

        affected_files = await run_git_command(command)
        paths = [
            relative_file.replace("profile_library", "custom_components/powercalc/data"),
            relative_file.replace("profile_library", "data"),
            relative_file,
        ]
        if any(path in affected_files.splitlines() for path in paths):
            return await get_commit_author(commit)
    return None


async def main_async() -> None:
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


def is_number(value: float | str | None) -> bool:
    """Try to convert value to a float."""
    if value is None:
        return False
    try:
        fvalue = float(value)
    except ValueError:
        return False
    return math.isfinite(fvalue)


def main() -> None:
    """Entry point that runs the async main function"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
