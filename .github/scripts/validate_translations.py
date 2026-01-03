#!/usr/bin/env python3

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

def extract_placeholders(text: str) -> set[str]:
    """
    Extract all placeholders in the format {name} from a string.

    Args:
        text: The string to extract placeholders from

    Returns:
        A set of placeholder names without the braces
    """
    if not isinstance(text, str):
        return set()

    # Find all occurrences of {name}
    placeholders = re.findall(r'\{([^{}]+)\}', text)
    return set(placeholders)

def extract_all_placeholders(data: dict, path: str = "") -> dict[str, set[str]]:
    """
    Recursively extract all placeholders from a nested dictionary.

    Args:
        data: The dictionary to extract placeholders from
        path: The current path in the dictionary (for tracking)

    Returns:
        A dictionary mapping paths to sets of placeholders
    """
    result = {}

    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key

        if isinstance(value, dict):
            # Recursively process nested dictionaries
            nested_result = extract_all_placeholders(value, current_path)
            result.update(nested_result)
        elif isinstance(value, str):
            # Extract placeholders from string values
            placeholders = extract_placeholders(value)
            if placeholders:
                result[current_path] = placeholders

    return result

def validate_translations(translations_dir: Path) -> list[str]:
    """
    Validate that all placeholders in en.json exist in all other translation files.

    Args:
        translations_dir: Path to the directory containing translation files

    Returns:
        A list of error messages for missing placeholders
    """

    en_file = translations_dir / "en.json"
    if not en_file.exists():
        return ["Error: en.json not found in the translations directory"]

    with open(en_file, 'r', encoding='utf-8') as f:
        en_data = json.load(f)

    en_placeholders = extract_all_placeholders(en_data)

    errors: list[str] = []

    translation_files = [f for f in translations_dir.glob("*.json") if f.name != "en.json"]

    for translation_file in translation_files:
        lang_code = translation_file.stem

        try:
            with open(translation_file, 'r', encoding='utf-8') as f:
                lang_data = json.load(f)
        except json.JSONDecodeError:
            errors.append(f"Error: {lang_code}.json is not a valid JSON file")
            continue

        lang_placeholders = extract_all_placeholders(lang_data)

        for path, en_path_placeholders in en_placeholders.items():
            path_parts = path.split('.')

            current = lang_data
            path_exists = True

            for part in path_parts:
                if part not in current:
                    path_exists = False
                    errors.append(f"Missing path in {lang_code}.json: {path}")
                    break
                current = current[part]

            if not path_exists:
                continue

            if path in lang_placeholders:
                lang_path_placeholders = lang_placeholders[path]
                missing_placeholders = en_path_placeholders - lang_path_placeholders

                if missing_placeholders:
                    placeholders_str = ", ".join([f"{{{p}}}" for p in missing_placeholders])
                    errors.append(f"Missing placeholders in {lang_code}.json at path {path}: {placeholders_str}")
            else:
                if isinstance(current, str):
                    placeholders_str = ", ".join([f"{{{p}}}" for p in en_path_placeholders])
                    errors.append(f"Missing placeholders in {lang_code}.json at path {path}: {placeholders_str}")

    return errors

def main():
    repo_root = Path(__file__).parent.parent.parent

    translations_dir = repo_root / "custom_components" / "powercalc" / "translations"

    if not translations_dir.exists():
        print(f"Error: Translations directory not found at {translations_dir}")
        sys.exit(1)

    print(f"Validating translations in {translations_dir}")

    errors = validate_translations(translations_dir)

    if errors:
        print("\nErrors found:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("\nAll translations are valid! No missing placeholders found.")
        sys.exit(0)

if __name__ == "__main__":
    main()
