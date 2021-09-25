from __future__ import annotations

import re
from typing import NamedTuple

import homeassistant.helpers.entity_registry as er
import voluptuous as vol


class SourceEntity(NamedTuple):
    unique_id: str
    object_id: str
    entity_id: str
    name: str
    domain: str
    supported_color_modes: list
    entity_entry: er.RegistryEntry | None


def validate_name_pattern(value: str) -> str:
    """Validate that the naming pattern contains {}."""
    regex = re.compile(r"\{\}")
    if not regex.search(value):
        raise vol.Invalid("Naming pattern must contain {}")
    return value
