from collections.abc import Generator
import gzip
import json
import os
from pathlib import Path
from typing import Any, TextIO

PROFILE_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../profile_library")


def open_lut_file(path: Path) -> TextIO:
    """Open a LUT CSV for reading, transparently decompressing gzipped files.

    Some contributed LUTs carry a UTF-8 BOM, which would otherwise end up in the first
    column name, so decode them with the BOM aware codec.
    """
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig")

    return path.open(encoding="utf-8-sig")


def _path_part(path_parts: list[str], index: int) -> str | None:
    """Return the path part at the given index, when available."""
    return path_parts[index] if len(path_parts) > index else None


def _read_model_json(directory: str, root: str, file_name: str) -> dict[str, Any]:
    """Read a single model.json file and enrich it with the profile identifiers from its path."""
    full_path = os.path.join(root, file_name)
    path_parts = os.path.relpath(root, directory).split(os.sep)

    with open(full_path) as f:
        data = json.load(f)

    return {
        "full_path": full_path,
        "data": data,
        "manufacturer": _path_part(path_parts, 0),
        "model": _path_part(path_parts, 1),
        "sub_profile": _path_part(path_parts, 2),
    }


def find_model_json_files(directory: str | None = None) -> Generator[dict[str, Any]]:
    """Recursively find all model.json files in a directory."""
    if directory is None:
        directory = PROFILE_DIRECTORY

    for root, _, files in os.walk(directory):
        for file in files:
            if file == "model.json":
                yield _read_model_json(directory, root, file)
