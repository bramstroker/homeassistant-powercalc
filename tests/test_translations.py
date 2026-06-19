from __future__ import annotations

import json
from pathlib import Path
import re
from typing import cast

TRANSLATIONS_DIR = Path("custom_components/powercalc/translations")
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def test_translated_strings_keep_english_placeholders() -> None:
    english_strings = _flatten_strings(_load_translation("en.json"))

    for translation_file in TRANSLATIONS_DIR.glob("*.json"):
        if translation_file.name == "en.json":
            continue

        translated_strings = _flatten_strings(_load_translation(translation_file.name))
        for path, translated_value in translated_strings.items():
            english_value = english_strings.get(path)
            if not english_value:
                continue

            assert _placeholders(translated_value) == _placeholders(english_value), f"{translation_file.name}: {path}"


def _load_translation(file_name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((TRANSLATIONS_DIR / file_name).read_text()))


def _flatten_strings(value: object, path: str = "") -> dict[str, str]:
    if isinstance(value, str):
        return {path: value}

    if not isinstance(value, dict):
        return {}

    strings: dict[str, str] = {}
    for key, child_value in value.items():
        child_path = f"{path}.{key}" if path else key
        strings.update(_flatten_strings(child_value, child_path))

    return strings


def _placeholders(value: str) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(value))
