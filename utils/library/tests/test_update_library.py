from __future__ import annotations

import asyncio
from pathlib import Path

from utils.library.update_library import get_color_modes


def test_get_color_modes_only_includes_known_lut_color_modes(tmp_path: Path) -> None:
    for filename in ("brightness.csv.gz", "color_temp.csv", "effect.csv.gz", "tapering.csv.gz"):
        (tmp_path / filename).touch()

    assert asyncio.run(get_color_modes(str(tmp_path))) == {"brightness", "color_temp", "effect"}
