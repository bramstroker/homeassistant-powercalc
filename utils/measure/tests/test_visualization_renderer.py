from __future__ import annotations

from pathlib import Path

from measure.visualization import build_plot_from_file
from measure.visualization.renderer import render_plot
import pytest

pytest.importorskip("matplotlib")


def test_matplotlib_renderer_writes_png(tmp_path: Path) -> None:
    source = tmp_path / "brightness.csv"
    output = tmp_path / "brightness.png"
    source.write_text("bri,watt\n1,0.5\n255,8.2\n", encoding="utf-8")

    render_plot(build_plot_from_file(source), output)

    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
