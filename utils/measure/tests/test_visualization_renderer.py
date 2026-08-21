import json
from pathlib import Path

from measure.visualization import build_composite_diagram_from_file, build_plot_from_file
from measure.visualization.renderer import render_composite_diagram, render_plot
import pytest

pytest.importorskip("matplotlib")


def test_matplotlib_renderer_writes_png(tmp_path: Path) -> None:
    source = tmp_path / "brightness.csv"
    output = tmp_path / "brightness.png"
    source.write_text("bri,watt\n1,0.5\n255,8.2\n", encoding="utf-8")

    render_plot(build_plot_from_file(source), output)

    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_matplotlib_renderer_writes_reproducible_svg(tmp_path: Path) -> None:
    source = tmp_path / "brightness.csv"
    source.write_text("bri,watt\n1,0.5\n255,8.2\n", encoding="utf-8")
    plot = build_plot_from_file(source)
    first = tmp_path / "first.svg"
    second = tmp_path / "second.svg"

    render_plot(plot, first)
    render_plot(plot, second)

    assert first.read_text(encoding="utf-8").lstrip().startswith("<?xml")
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize("mode", ["stop_at_first", "sum_all"])
def test_matplotlib_renderer_writes_composite_diagram(tmp_path: Path, mode: str) -> None:
    source = tmp_path / "model.json"
    output = tmp_path / f"{mode}.png"
    source.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": {
                    "mode": mode,
                    "strategies": [
                        {"condition": {"condition": "state", "state": "on"}, "fixed": {"power": 2}},
                        {"fixed": {"power": 1}},
                    ],
                },
            },
        ),
        encoding="utf-8",
    )

    render_composite_diagram(build_composite_diagram_from_file(source), output)

    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_matplotlib_renderer_writes_reproducible_composite_svg(tmp_path: Path) -> None:
    source = tmp_path / "model.json"
    source.write_text(
        '{"calculation_strategy":"composite","composite_config":[{"fixed":{"power":2}}]}',
        encoding="utf-8",
    )
    diagram = build_composite_diagram_from_file(source)
    first = tmp_path / "first.svg"
    second = tmp_path / "second.svg"

    render_composite_diagram(diagram, first)
    render_composite_diagram(diagram, second)

    assert first.read_bytes() == second.read_bytes()
