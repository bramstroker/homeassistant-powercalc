import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

from measure.visualization import (
    PlotKind,
    PlotPoint,
    PlotSeries,
    PlotSpec,
    build_composite_diagram_from_file,
    build_plot_from_file,
)
from measure.visualization.diagram import CompositeBranch, CompositeDiagramSpec, CompositeMode
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


def test_interactive_plot_displays_labelled_line_and_closes_figure(monkeypatch: pytest.MonkeyPatch) -> None:
    import matplotlib.pyplot as plt

    plot = PlotSpec(
        id="calibration",
        title="Charging calibration",
        kind=PlotKind.LINE,
        x_label="Battery (%)",
        y_label="Power (W)",
        source="model.json",
        series=[PlotSeries(label="Charging", color="#123456", points=[PlotPoint(0, 30), PlotPoint(100, 2)])],
    )
    show = MagicMock()

    def inspect_displayed_plot() -> None:
        axes = plt.gcf().axes[0]
        assert axes.get_title() == "Charging calibration"
        assert axes.get_xlabel() == "Battery (%)"
        assert axes.get_ylabel() == "Power (W)"
        assert axes.get_legend().get_texts()[0].get_text() == "Charging"
        assert axes.lines[0].get_color() == "#123456"
        assert list(axes.lines[0].get_ydata()) == [30, 2]

    show.side_effect = inspect_displayed_plot
    monkeypatch.setattr(plt, "show", show)
    previous_figures = plt.get_fignums()

    render_plot(plot)

    show.assert_called_once_with()
    assert plt.get_fignums() == previous_figures


def test_interactive_composite_diagram_displays_strategy_without_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import matplotlib.pyplot as plt

    diagram = CompositeDiagramSpec(
        title="Vacuum activities",
        mode=CompositeMode.STOP_AT_FIRST,
        source="model.json",
        branches=[CompositeBranch(index=1, condition=None, strategy="Fixed", detail=None)],
    )
    show = MagicMock()

    def inspect_displayed_diagram() -> None:
        labels = [text.get_text() for text in plt.gcf().axes[0].texts]
        assert "#1  Always" in labels
        assert "Fixed" in labels

    show.side_effect = inspect_displayed_diagram
    monkeypatch.setattr(plt, "show", show)
    previous_figures = plt.get_fignums()

    render_composite_diagram(diagram)

    show.assert_called_once_with()
    assert plt.get_fignums() == previous_figures


@pytest.mark.parametrize("output", [None, Path("plot.png")])
def test_renderer_explains_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch, output: Path | None) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    plot = PlotSpec(
        id="brightness",
        title="Brightness",
        kind=PlotKind.SCATTER,
        x_label="Brightness",
        y_label="Power (W)",
        source="brightness.csv",
        series=[],
    )

    with pytest.raises(RuntimeError, match="Run with `uv run --group visualize`") as raised:
        render_plot(plot, output)

    assert isinstance(raised.value.__cause__, ImportError)
