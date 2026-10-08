import json
import os
from pathlib import Path
import tempfile
from typing import Any


def write_bytes_atomic(path: Path, content: bytes) -> None:
    """Replace a file via a temporary sibling, cleaning up even if writing fails."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:  # pragma: no branch - no temporary exists only when creation raises
            temporary.unlink(missing_ok=True)


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
            # ``default`` keeps documents holding enums or timestamps writable; payloads that
            # already went through ``model_dump(mode="json")`` never reach it.
            json.dump(value, handle, indent=2, sort_keys=True, default=str)
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
