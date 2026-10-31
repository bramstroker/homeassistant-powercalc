"""Read model data with the same sub-profile overrides as Powercalc."""

import json
from pathlib import Path


def load_model_data(path: Path) -> object:
    data = json.loads(path.read_text(encoding="utf-8"))
    parent_path = path.parent.parent / "model.json"
    if path.name != "model.json" or not isinstance(data, dict) or not parent_path.is_file():
        return data

    parent_data = json.loads(parent_path.read_text(encoding="utf-8"))
    if not isinstance(parent_data, dict):
        return data
    return {**parent_data, **data}
