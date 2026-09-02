"""Helpers for links to the public power profile library."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

from custom_components.powercalc.const import LIBRARY_URL


def _slugify(value: str) -> str:
    """Create a slug matching the public library routes."""
    normalized = "".join(
        character for character in unicodedata.normalize("NFKD", value) if not unicodedata.combining(character)
    )
    return re.sub(r"[\W_]+", "-", normalized.lower(), flags=re.UNICODE).strip("-")


def profile_url(manufacturer: str, model: str) -> str:
    """Return the canonical public library URL for a power profile."""
    manufacturer_slug = quote(_slugify(manufacturer), safe="")
    model_slug = quote(_slugify(model), safe="")
    return f"{LIBRARY_URL}/profiles/{manufacturer_slug}/{model_slug}"
