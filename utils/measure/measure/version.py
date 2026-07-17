from __future__ import annotations

from pathlib import Path

from measure.const import PROJECT_DIR


def measure_version() -> str:
    return (Path(PROJECT_DIR) / ".VERSION").read_text(encoding="utf-8").strip()
