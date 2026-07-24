from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, value: dict[str, Any], *, private: bool = False) -> None:
    """Write JSON to ``path`` atomically; ``private`` keeps the file owner-only (0600) at every step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        if private:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
        else:
            handle = temporary.open("w", encoding="utf-8")
        with handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            os.chmod(temporary, 0o600)
        temporary.replace(path)
        if private:
            os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
