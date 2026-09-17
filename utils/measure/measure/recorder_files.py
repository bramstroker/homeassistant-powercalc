from collections.abc import Iterable
from pathlib import Path
import re

from measure.runner.const import COMPLEX_PROFILE_EXPORT_FILENAME


def recording_filenames(names: Iterable[str], filename: str = COMPLEX_PROFILE_EXPORT_FILENAME) -> tuple[str, ...]:
    """Select numbered runs in chronological order, followed by the latest file."""
    names = set(names)
    base = Path(filename)
    pattern = re.compile(rf"{re.escape(base.stem)}-([1-9][0-9]*){re.escape(base.suffix)}")
    archived = {int(match[1]): name for name in names if (match := pattern.fullmatch(name)) is not None}
    ordered = tuple(archived[index] for index in sorted(archived))
    return (*ordered, filename) if filename in names else ordered
