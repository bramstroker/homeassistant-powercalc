from __future__ import annotations

import json
from pathlib import Path

from measure.visualization import PlotKind, PlotSpec, cli
import pytest


def test_resolve_plot_input_finds_profile_library_path() -> None:
    path = cli.resolve_plot_input("ledvance/4058075729223/brightness.csv.gz")

    assert path.name == "brightness.csv.gz"
    assert path.parent.name == "4058075729223"


def test_generate_directory_plots_writes_supported_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brightness = tmp_path / "acme" / "lamp" / "brightness.csv.gz"
    model = tmp_path / "acme" / "speaker" / "model.json"
    unsupported = tmp_path / "acme" / "lamp" / "unknown.csv.gz"
    brightness.parent.mkdir(parents=True)
    model.parent.mkdir(parents=True)
    brightness.write_bytes(b"content")
    unsupported.write_bytes(b"content")
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "linear",
                "linear_config": {"calibrate": ["0 -> 1.0", "100 -> 5.0"]},
            },
        ),
        encoding="utf-8",
    )
    rendered: list[Path] = []

    monkeypatch.setattr(cli, "build_plot_from_file", lambda path: _plot(path))
    monkeypatch.setattr(cli, "render_plot", lambda _plot, output: rendered.append(output))

    generated = cli.generate_directory_plots(tmp_path)

    assert generated == 2
    assert rendered == [
        tmp_path / "acme" / "lamp" / "brightness.png",
        tmp_path / "acme" / "speaker" / "calibration.png",
    ]


def test_generate_directory_plots_skips_existing_output_unless_forced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brightness = tmp_path / "brightness.csv"
    output = tmp_path / "brightness.png"
    brightness.write_text("bri,watt\n1,1.0\n", encoding="utf-8")
    output.write_bytes(b"existing")
    rendered: list[Path] = []
    monkeypatch.setattr(cli, "render_plot", lambda _plot, path: rendered.append(path))

    assert cli.generate_directory_plots(tmp_path) == 0
    assert cli.generate_directory_plots(tmp_path, force=True) == 1
    assert rendered == [output]


def _plot(source: Path) -> PlotSpec:
    return PlotSpec(
        id=source.stem,
        title=source.stem,
        kind=PlotKind.SCATTER,
        x_label="Value",
        y_label="Power (W)",
        source=str(source),
        series=(),
    )
