import gzip
import json
from pathlib import Path
import runpy
import sys

from measure.visualization import CompositeDiagramSpec, PlotSpec, pr_plots
import pytest


def write_model(directory: Path, data: object) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model.json"
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("changed", ["parent", "child", "both"])
def test_generates_sub_profile_plots_for_parent_and_child_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    checkout = tmp_path / "pr"
    model = checkout / "profile_library" / "roborock" / "S10R51-01"
    parent = write_model(model, {"calculation_strategy": "composite", "device_type": "vacuum_robot"})
    children = [
        write_model(
            model / variant,
            {
                "composite_config": [
                    {"fixed": {"power": power}},
                    {"linear": {"calibrate": ["15 -> 23", "99 -> 16"]}},
                ],
            },
        )
        for variant, power in [("hot", 265), ("warm", 190), ("room_temperature", 5)]
    ]
    changed_paths = [parent] if changed == "parent" else [children[0]]
    if changed == "both":
        changed_paths.extend([parent, children[0]])
    rendered: dict[Path, PlotSpec | CompositeDiagramSpec] = {}
    monkeypatch.setattr(pr_plots, "render_plot", lambda plot, output: rendered.__setitem__(output, plot))
    monkeypatch.setattr(
        pr_plots, "render_composite_diagram", lambda diagram, output: rendered.__setitem__(output, diagram)
    )
    output = tmp_path / "artifacts"

    generated = pr_plots.generate_pr_plots(
        checkout, [str(path.relative_to(checkout)) for path in changed_paths], output
    )

    variants = ["hot"] if changed == "child" else ["hot", "warm", "room_temperature"]
    assert generated == len(variants) * 2
    assert set(rendered) == {
        output / "roborock" / "S10R51-01" / variant / name
        for variant in variants
        for name in ["calibration.png", "composite.png"]
    }
    for path, plot in rendered.items():
        if isinstance(plot, PlotSpec):
            assert plot.title == "Charging calibration"
            assert plot.x_label == "Battery level (%)"
        else:
            power = {"hot": "265 W", "warm": "190 W", "room_temperature": "5 W"}[path.parent.name]
            assert plot.branches[0].detail == power


@pytest.mark.parametrize("compressed", [False, True])
def test_preserves_standalone_models_and_light_plots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, compressed: bool
) -> None:
    library = tmp_path / "profile_library" / "acme"
    linear = write_model(
        library / "speaker",
        {"calculation_strategy": "linear", "linear_config": {"calibrate": ["0 -> 1", "100 -> 5"]}},
    )
    composite = write_model(
        library / "fan",
        {"calculation_strategy": "composite", "composite_config": [{"fixed": {"power": 5}}]},
    )
    brightness = library / "lamp" / ("brightness.csv.gz" if compressed else "brightness.csv")
    brightness.parent.mkdir()
    data = b"bri,watt\n1,1.5\n"
    brightness.write_bytes(gzip.compress(data) if compressed else data)
    rendered: list[Path] = []
    monkeypatch.setattr(pr_plots, "render_plot", lambda _plot, output: rendered.append(output))
    monkeypatch.setattr(pr_plots, "render_composite_diagram", lambda _diagram, output: rendered.append(output))
    output = tmp_path / "artifacts"

    assert (
        pr_plots.generate_pr_plots(
            tmp_path, [str(path.relative_to(tmp_path)) for path in [linear, composite, brightness]], output
        )
        == 3
    )
    assert set(rendered) == {
        output / "acme" / "speaker" / "calibration.png",
        output / "acme" / "fan" / "composite.png",
        output / "acme" / "lamp" / "brightness.png",
    }


def test_ignores_removed_unsupported_and_unplottable_files(tmp_path: Path) -> None:
    fixed = write_model(tmp_path / "profile_library" / "acme" / "plug", {"calculation_strategy": "fixed"})
    unsupported = fixed.with_name("notes.txt")
    unsupported.write_text("notes")
    manufacturer = tmp_path / "profile_library" / "acme" / "manufacturer.json"
    manufacturer.write_text("{}")
    changed = [
        str(path.relative_to(tmp_path))
        for path in [fixed, unsupported, manufacturer, fixed.with_name("brightness.csv")]
    ]
    changed.append("README.md")

    assert pr_plots.generate_pr_plots(tmp_path, changed, tmp_path / "artifacts") == 0
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize("filename", ["/profile_library/acme/model/model.json", "profile_library/../model/model.json"])
def test_rejects_paths_outside_checkout(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ValueError, match="Invalid changed file path"):
        pr_plots.generate_pr_plots(tmp_path, [filename], tmp_path / "artifacts")


def test_cli_generates_plots_and_reports_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    model = write_model(
        tmp_path / "profile_library" / "acme" / "plug",
        {"calculation_strategy": "composite", "composite_config": [{"fixed": {"power": 5}}]},
    )
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps([str(model.relative_to(tmp_path))]))
    rendered: list[Path] = []
    monkeypatch.setattr(pr_plots, "render_composite_diagram", lambda _diagram, output: rendered.append(output))

    pr_plots.main(
        [
            "--checkout-root",
            str(tmp_path),
            "--changed-files",
            str(changed),
            "--output-directory",
            str(tmp_path / "output"),
        ],
    )

    assert rendered == [tmp_path / "output" / "acme" / "plug" / "composite.png"]
    assert capsys.readouterr().out == "Generated 1 plot(s).\n"


def test_module_entry_point_writes_png_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("matplotlib")
    model = write_model(
        tmp_path / "profile_library" / "acme" / "plug",
        {"calculation_strategy": "composite", "composite_config": [{"fixed": {"power": 5}}]},
    )
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps([str(model.relative_to(tmp_path))]))
    output = tmp_path / "artifacts"
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_plots",
            "--checkout-root",
            str(tmp_path),
            "--changed-files",
            str(changed),
            "--output-directory",
            str(output),
        ],
    )
    monkeypatch.delitem(sys.modules, "measure.visualization.pr_plots")

    runpy.run_module("measure.visualization.pr_plots", run_name="__main__")

    assert (output / "acme" / "plug" / "composite.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert capsys.readouterr().out.endswith("Generated 1 plot(s).\n")


@pytest.mark.parametrize("data", [{}, [1]])
def test_cli_rejects_invalid_changed_file_lists(
    tmp_path: Path, data: object, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(data))

    with pytest.raises(SystemExit) as raised:
        pr_plots.main(
            [
                "--checkout-root",
                str(tmp_path),
                "--changed-files",
                str(changed),
                "--output-directory",
                str(tmp_path / "output"),
            ],
        )

    assert raised.value.code == 2
    assert "JSON array of file paths" in capsys.readouterr().err
