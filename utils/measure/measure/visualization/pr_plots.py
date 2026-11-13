"""Generate PNG artifacts for changed profile files using trusted plotting code."""

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from measure.visualization import (
    build_composite_diagram_from_file,
    build_plot_from_file,
    model_has_composite_branches,
    model_has_linear_calibration,
)
from measure.visualization.profile import load_model_data
from measure.visualization.renderer import render_composite_diagram, render_plot

_LIGHT_PLOT_FILES = {
    f"{mode}.csv{suffix}" for mode in ["brightness", "color_temp", "hs", "effect"] for suffix in ["", ".gz"]
}


def collect_plot_inputs(checkout_root: Path, changed_files: list[str]) -> list[Path]:
    """Include sub-profiles when their inherited parent model changes."""
    inputs: set[Path] = set()
    for filename in changed_files:
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid changed file path: {filename}")
        if len(relative.parts) < 4 or relative.parts[0] != "profile_library":
            continue
        source = checkout_root / relative
        if not source.is_file():
            continue
        if source.name == "model.json":
            inputs.add(relative)
            if len(relative.parts) == 4:
                inputs.update(child.relative_to(checkout_root) for child in source.parent.glob("*/model.json"))
        elif source.name in _LIGHT_PLOT_FILES:
            inputs.add(relative)
    return sorted(inputs)


def generate_pr_plots(checkout_root: Path, changed_files: list[str], output_directory: Path) -> int:
    generated = 0
    for relative in collect_plot_inputs(checkout_root, changed_files):
        source = checkout_root / relative
        destination = output_directory / relative.relative_to("profile_library").parent
        if source.name == "model.json":
            data = load_model_data(source)
            if model_has_composite_branches(data):
                render_composite_diagram(build_composite_diagram_from_file(source), destination / "composite.png")
                generated += 1
            if model_has_linear_calibration(data):
                render_plot(build_plot_from_file(source), destination / "calibration.png")
                generated += 1
        else:
            name = source.name.removesuffix(".gz").removesuffix(".csv")
            render_plot(build_plot_from_file(source), destination / f"{name}.png")
            generated += 1
    return generated


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    changed_files = json.loads(args.changed_files.read_text(encoding="utf-8"))
    if not isinstance(changed_files, list) or any(not isinstance(path, str) for path in changed_files):
        parser.error("--changed-files must contain a JSON array of file paths")
    generated = generate_pr_plots(args.checkout_root, changed_files, args.output_directory)
    print(f"Generated {generated} plot(s).")


if __name__ == "__main__":
    main()
