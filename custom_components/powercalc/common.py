from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, NamedTuple

import attr
import voluptuous as vol


class SourceEntity(NamedTuple):
    unique_id: str
    object_id: str
    entity_id: str
    name: str
    domain: str
    capabilities: Mapping[str, Any] | None = attr.ib(default=None)


def validate_name_pattern(value: str) -> str:
    """Validate that the naming pattern contains {}."""
    regex = re.compile(r"\{\}")
    if not regex.search(value):
        raise vol.Invalid("Naming pattern must contain {}")
    return value
