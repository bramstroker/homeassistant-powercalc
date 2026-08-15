from pathlib import Path
from typing import Any

from measure.visualization import PlotKind, PlotSeries, PlotSpec

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
