from pathlib import Path
import textwrap
from typing import Any

from measure.visualization.core import PlotKind, PlotSeries, PlotSpec
from measure.visualization.diagram import CompositeDiagramSpec, CompositeMode

_DEFAULT_COLOR = "#5488e8"


def render_plot(plot: PlotSpec, output: Path | None = None) -> None:
    """Render a plot specification with the optional scientific dependency group."""

    plt = _pyplot(output)
    figure, axes = plt.subplots(figsize=(10, 6))
    for series in plot.series:
        _draw_series(axes, plot.kind, series)
    axes.set_title(plot.title)
    axes.set_xlabel(plot.x_label)
    axes.set_ylabel(plot.y_label)
    axes.grid(True, alpha=0.25)
    if any(series.label for series in plot.series):
        axes.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)
    figure.tight_layout()
    if output is None:
        plt.show()
    else:
        _save_figure(figure, output)
    plt.close(figure)


def render_composite_diagram(diagram: CompositeDiagramSpec, output: Path | None = None) -> None:
    """Render the evaluation flow for a composite profile."""

    plt = _pyplot(output)
    branch_count = len(diagram.branches)
    figure, axes = plt.subplots(figsize=(12, max(4.5, 2.0 + branch_count * 1.65)))
    axes.set_xlim(0, 14.5)
    axes.set_ylim(-1.0, branch_count * 1.65 + 1.15)
    axes.axis("off")
    figure.suptitle(diagram.title, fontsize=16, y=0.98)
    mode_label = (
        "Stop at first · branches are evaluated from top to bottom"
        if diagram.mode is CompositeMode.STOP_AT_FIRST
        else "Sum all · every matching branch contributes to the result"
    )
    axes.text(7, branch_count * 1.65 + 0.55, mode_label, ha="center", va="center", color="#555555")

    if diagram.mode is CompositeMode.STOP_AT_FIRST:
        _draw_stop_at_first(axes, diagram)
    else:
        _draw_sum_all(axes, diagram)

    figure.tight_layout(rect=(0, 0, 1, 0.95))
    if output is None:
        plt.show()
    else:
        _save_figure(figure, output)
    plt.close(figure)


def _draw_stop_at_first(axes: Any, diagram: CompositeDiagramSpec) -> None:  # noqa: ANN401
    branch_y = [_branch_y(len(diagram.branches), index) for index in range(len(diagram.branches))]
    for position, (branch, y_value) in enumerate(zip(diagram.branches, branch_y, strict=True)):
        condition = branch.condition or "Always"
        _add_box(axes, 1.1, y_value, 5.7, 1.0, f"#{branch.index}  {condition}", kind="condition")
        _add_arrow(axes, (6.8, y_value + 0.5), (8.0, y_value + 0.5), "match" if branch.condition else None)
        _add_box(axes, 8.0, y_value, 3.9, 1.0, _strategy_label(branch.strategy, branch.detail), kind="strategy")
        _add_arrow(axes, (11.9, y_value + 0.5), (13.2, y_value + 0.5), "return")

        if branch.condition and position + 1 < len(branch_y):
            next_y = branch_y[position + 1]
            _add_arrow(axes, (3.95, y_value), (3.95, next_y + 1.0), "no match")


def _draw_sum_all(axes: Any, diagram: CompositeDiagramSpec) -> None:  # noqa: ANN401
    branch_y = [_branch_y(len(diagram.branches), index) for index in range(len(diagram.branches))]
    top = branch_y[0] + 1.0
    bottom = branch_y[-1] + 0.5
    axes.plot([0.75, 0.75], [bottom, top], color="#888888", linewidth=1.2)
    axes.plot([13.0, 13.0], [bottom, top], color="#888888", linewidth=1.2)

    for branch, y_value in zip(diagram.branches, branch_y, strict=True):
        _add_arrow(axes, (0.75, y_value + 0.5), (1.1, y_value + 0.5))
        condition = branch.condition or "Always"
        _add_box(axes, 1.1, y_value, 5.7, 1.0, f"#{branch.index}  {condition}", kind="condition")
        _add_arrow(axes, (6.8, y_value + 0.5), (8.0, y_value + 0.5), "match" if branch.condition else None)
        _add_box(axes, 8.0, y_value, 3.9, 1.0, _strategy_label(branch.strategy, branch.detail), kind="strategy")
        _add_arrow(axes, (11.9, y_value + 0.5), (13.0, y_value + 0.5), "add")

    _add_arrow(axes, (13.0, bottom), (13.0, -0.1))
    _add_box(axes, 11.8, -0.85, 2.4, 0.75, "Summed power", kind="result")


def _branch_y(branch_count: int, position: int) -> float:
    return (branch_count - position - 1) * 1.65


def _strategy_label(strategy: str, detail: str | None) -> str:
    return strategy if detail is None else f"{strategy}\n{detail}"


def _add_box(
    axes: Any,  # noqa: ANN401
    x_value: float,
    y_value: float,
    width: float,
    height: float,
    label: str,
    *,
    kind: str,
) -> None:
    from matplotlib.patches import FancyBboxPatch

    colors = {
        "condition": ("#eef3fc", "#5488e8"),
        "strategy": ("#edf8f3", "#3aa17e"),
        "result": ("#f5f1fb", "#8c67bd"),
    }
    facecolor, edgecolor = colors[kind]
    box = FancyBboxPatch(
        (x_value, y_value),
        width,
        height,
        boxstyle="round,pad=0.04,rounding_size=0.08",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.4,
    )
    axes.add_patch(box)
    axes.text(
        x_value + width / 2,
        y_value + height / 2,
        textwrap.fill(label, width=42),
        ha="center",
        va="center",
        fontsize=10,
        color="#202124",
    )


def _add_arrow(
    axes: Any,  # noqa: ANN401
    start: tuple[float, float],
    end: tuple[float, float],
    label: str | None = None,
) -> None:
    from matplotlib.patches import FancyArrowPatch

    arrow = FancyArrowPatch(start, end, arrowstyle="-|>", color="#777777", linewidth=1.1, mutation_scale=10)
    axes.add_patch(arrow)
    if label:
        x_value = (start[0] + end[0]) / 2
        y_value = (start[1] + end[1]) / 2
        axes.text(x_value, y_value + 0.12, label, ha="center", va="bottom", fontsize=8, color="#666666")


def _pyplot(output: Path | None) -> Any:  # noqa: ANN401
    """Import pyplot, switching to a deterministic headless backend when writing a file."""

    try:
        import matplotlib as mpl

        if output is not None:
            mpl.use("Agg")
            if _is_svg(output):
                # Element ids are salted per process, so an unchanged plot would otherwise
                # render to different bytes on every run and churn the committed SVGs.
                mpl.rcParams["svg.hashsalt"] = "powercalc"
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "Matplotlib is required for image rendering. Run with `uv run --group visualize`.",
        ) from error
    return plt


def _draw_series(axes: Any, kind: PlotKind, series: PlotSeries) -> None:  # noqa: ANN401
    """Draw one series as a connected line or as individually coloured points."""

    x_values = [point.x for point in series.points]
    y_values = [point.y for point in series.points]
    color = series.color or _DEFAULT_COLOR
    if kind is PlotKind.LINE:
        axes.plot(x_values, y_values, color=color, marker="o", linestyle="-", label=series.label)
    else:
        point_colors = [point.color or color for point in series.points]
        axes.scatter(x_values, y_values, color=point_colors, marker=".", s=10, label=series.label)


def _save_figure(figure: Any, output: Path) -> None:  # noqa: ANN401
    """Write the figure, keeping SVG output byte-stable across runs."""

    output.parent.mkdir(parents=True, exist_ok=True)
    if _is_svg(output):
        # Matplotlib stamps the current date into SVG metadata; drop it for the same reason.
        figure.savefig(output, metadata={"Date": None})
    else:
        figure.savefig(output)
    print(f"Save plot to {output}")


def _is_svg(output: Path) -> bool:
    return output.suffix.lower() == ".svg"
