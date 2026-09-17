from collections.abc import Iterable
from pathlib import Path
import re

DEFAULT_EXPORT_FILENAME = "record.csv"
COMPLEX_PROFILE_EXPORT_FILENAME = "record.jsonl"


def recording_filenames(names: Iterable[str], filename: str = COMPLEX_PROFILE_EXPORT_FILENAME) -> tuple[str, ...]:
    """Select numbered runs in chronological order, followed by the latest file."""
    names = set(names)
    base = Path(filename)
    pattern = re.compile(rf"{re.escape(base.stem)}-([1-9][0-9]*){re.escape(base.suffix)}")
    archived = {int(match[1]): name for name in names if (match := pattern.fullmatch(name)) is not None}
    ordered = tuple(archived[index] for index in sorted(archived))
    return (*ordered, filename) if filename in names else ordered


def recording_paths(directory: Path, filename: str) -> tuple[Path, ...]:
    """Return numbered earlier runs followed by the latest recording."""
    names = (path.name for path in directory.glob("*") if path.is_file() and not path.is_symlink())
    return tuple(directory / name for name in recording_filenames(names, filename))
