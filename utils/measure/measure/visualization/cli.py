from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from measure.visualization import build_plot_from_file
from measure.visualization.renderer import render_plot

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
        output_path = _directory_output_path(input_path)
        if output_path.exists() and not force:
            continue
        render_plot(build_plot_from_file(input_path), output_path)
        generated += 1
    return generated


def _directory_plot_inputs(directory: Path) -> list[Path]:
    light_files = (path for path in directory.rglob("*.csv*") if path.name in _LIGHT_PLOT_FILES)
    linear_models = (path for path in directory.rglob("model.json") if _is_linear_model(path))
    return sorted((*light_files, *linear_models))


def _is_linear_model(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return False
    linear_config = data.get("linear_config")
    return (
        data.get("calculation_strategy") == "linear"
        and isinstance(linear_config, dict)
        and isinstance(linear_config.get("calibrate"), list)
    )


def _directory_output_path(input_path: Path) -> Path:
    if input_path.name == "model.json":
        return input_path.with_name("calibration.png")
    name = input_path.name.removesuffix(".gz").removesuffix(".csv")
    return input_path.with_name(f"{name}.png")


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
