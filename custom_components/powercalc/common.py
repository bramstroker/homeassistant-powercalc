from __future__ import annotations

from typing import Any, NamedTuple
from collections.abc import Iterable, Mapping

import attr


class SourceEntity(NamedTuple):
    unique_id: str
    object_id: str
    entity_id: str
    name: str
    domain: str
    capabilities: Mapping[str, Any] | None = attr.ib(default=None)