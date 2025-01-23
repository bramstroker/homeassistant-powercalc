import json
import os
from collections.abc import Generator

PROFILE_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../profile_library")


def find_model_json_files(directory: str | None = None) -> Generator:
    """Recursively find all model.json files in a directory."""
    if directory is None:
        directory = PROFILE_DIRECTORY

    for root, _, files in os.walk(directory):
        for file in files:
            if file == "model.json":
                full_path = os.path.join(root, file)

                path_parts = os.path.relpath(root, directory).split(os.sep)
                manufacturer = path_parts[0] if len(path_parts) > 0 else None
                model = path_parts[1] if len(path_parts) > 1 else None
                sub_profile = path_parts[2] if len(path_parts) > 2 else None

                with open(full_path) as f:
                    data = {
                        "full_path": full_path,
                        "data": json.load(f),
                        "manufacturer": manufacturer,
                        "model": model,
                        "sub_profile": sub_profile,
                    }
                yield data
