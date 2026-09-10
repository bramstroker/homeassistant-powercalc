"""Bounded readers for profile CSV data."""

import gzip
from io import BytesIO, TextIOWrapper
from typing import TextIO

from custom_components.powercalc.errors import StrategyConfigurationError

MAX_UNCOMPRESSED_SIZE = 10 * 1024 * 1024


def open_profile_csv(path: str) -> TextIO:
    """Reject oversized CSV data before exposing it to parsers."""
    open_func = gzip.open if path.endswith(".gz") else open
    with open_func(path, "rb") as source:
        # Bound the decompression itself, including concatenated gzip members.
        data = source.read(MAX_UNCOMPRESSED_SIZE + 1)
    if len(data) > MAX_UNCOMPRESSED_SIZE:
        raise StrategyConfigurationError(
            f"Profile data file '{path}' exceeds the uncompressed size limit of {MAX_UNCOMPRESSED_SIZE} bytes",
        )
    return TextIOWrapper(BytesIO(data), encoding="utf-8")
