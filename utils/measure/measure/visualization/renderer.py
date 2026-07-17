from __future__ import annotations

from pathlib import Path

from measure.visualization import PlotKind, PlotSpec

_DEFAULT_COLOR = "#5488e8"


def render_plot(plot: PlotSpec, output: Path | None = None) -> None:
    """Render a plot specification with the optional scientific dependency group."""

    try:
        import matplotlib as mpl

        if output is not None:
            mpl.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "Matplotlib is required for PNG rendering. Run with `uv run --group visualize`.",
        ) from error

    figure, axes = plt.subplots(figsize=(10, 6))
    for series in plot.series:
        x_values = [point.x for point in series.points]
        y_values = [point.y for point in series.points]
        color = series.color or _DEFAULT_COLOR
        if plot.kind is PlotKind.LINE:
            axes.plot(x_values, y_values, color=color, marker="o", linestyle="-", label=series.label)
        else:
            point_colors = [point.color or color for point in series.points]
            axes.scatter(x_values, y_values, color=point_colors, marker=".", s=10, label=series.label)
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
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output)
        print(f"Save plot to {output}")
    plt.close(figure)
