import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from measure.visualization import PlotSpec, build_plot_from_file, limit_plot_points, model_has_linear_calibration
from measure.visualization.renderer import render_plot

# Every marker stays a separate element in an SVG, so the largest LUTs (~25k rows) would
# write multi-megabyte files into the profile library. The PNGs keep the full measurement set.
_SVG_MAX_POINTS = 4_000
_LIGHT_PLOT_FILES = {
    "brightness.csv",
    "brightness.csv.gz",
    "color_temp.csv",
    "color_temp.csv.gz",
    "effect.csv",
    "effect.csv.gz",
    "hs.csv",
    "hs.csv.gz",
}


def resolve_plot_input(file_path: str) -> Path:
    """Resolve a direct path or a path relative to the profile library."""

    direct = Path(file_path)
    if direct.exists():
        return direct
    library_path = Path(__file__).resolve().parents[4] / "profile_library" / file_path
    if library_path.exists():
        return library_path
    raise FileNotFoundError(f"File not found: {file_path}")


def plot_output_path(input_path: Path, output: str | None) -> Path | None:
    if output is None:
        return None
    if output != "auto":
        return Path(output)
    name = input_path.name.removesuffix(".gz").removesuffix(".csv").removesuffix(".json")
    return Path(f"{name}.png")


def generate_directory_plots(directory: Path, *, force: bool = False) -> int:
    generated = 0
    for input_path in _directory_plot_inputs(directory):
        outputs = [path for path in _directory_output_paths(input_path) if force or not path.exists()]
        if not outputs:
            continue
        plot = build_plot_from_file(input_path)
        for output_path in outputs:
            render_plot(_plot_for_output(plot, output_path), output_path)
            generated += 1
    return generated


def _directory_plot_inputs(directory: Path) -> list[Path]:
    light_files = (path for path in directory.rglob("*.csv*") if path.name in _LIGHT_PLOT_FILES)
    linear_models = (path for path in directory.rglob("model.json") if _has_linear_calibration(path))
    return sorted((*light_files, *linear_models))


def _has_linear_calibration(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return False
    return model_has_linear_calibration(data)


def _directory_output_paths(input_path: Path) -> tuple[Path, ...]:
    if input_path.name == "model.json":
        name = "calibration"
    else:
        name = input_path.name.removesuffix(".gz").removesuffix(".csv")
    return tuple(input_path.with_name(f"{name}.{extension}") for extension in ("png", "svg"))


def _plot_for_output(plot: PlotSpec, output: Path) -> PlotSpec:
    if output.suffix == ".svg":
        return limit_plot_points(plot, _SVG_MAX_POINTS)
    return plot


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Output a Powercalc measurement artifact as a plot")
    parser.add_argument("path")
    parser.add_argument("--output")
    parser.add_argument("--colormode")
    parser.add_argument("--force", action="store_true", help="Overwrite plots when processing a directory")
    args = parser.parse_args(argv)
    input_path = resolve_plot_input(args.path)
    if input_path.is_dir():
        if args.output is not None or args.colormode is not None:
            parser.error("--output and --colormode can only be used with a file")
        generated = generate_directory_plots(input_path, force=args.force)
        print(f"Generated {generated} plot(s).")
        return
    plot = build_plot_from_file(input_path, color_mode=args.colormode)
    render_plot(plot, plot_output_path(input_path, args.output))
