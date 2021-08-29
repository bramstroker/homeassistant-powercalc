from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

import attr


class SourceEntity(NamedTuple):
    unique_id: str
    object_id: str
    entity_id: str
    name: str
    domain: str
    capabilities: Mapping[str, Any] | None = attr.ib(default=None)
