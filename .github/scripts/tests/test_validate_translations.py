import json
from pathlib import Path

from validate_translations import validate_translations


def test_translation_validation_reports_missing_paths_and_placeholders(tmp_path: Path) -> None:
    source = {
        "absent": "Hello {name}",
        "changed": "Hello {name} from {source}",
        "empty": "Hello {name}",
        "nested": "Hello {name}",
        "valid": "Hello {name}",
    }
    translation = {
        "changed": "Hallo {name}",
        "empty": "Hallo",
        "nested": {"child": "Hallo"},
        "valid": "Hallo {name}",
    }
    (tmp_path / "en.json").write_text(json.dumps(source), encoding="utf-8")
    (tmp_path / "nl.json").write_text(json.dumps(translation), encoding="utf-8")

    assert validate_translations(tmp_path) == [
        "Missing path in nl.json: absent",
        "Missing placeholders in nl.json at path changed: {source}",
        "Missing placeholders in nl.json at path empty: {name}",
    ]
