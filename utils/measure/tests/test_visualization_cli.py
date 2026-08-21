import json
from pathlib import Path

from measure.visualization import PlotKind, PlotSpec, cli
from measure.visualization.cli import _SVG_MAX_POINTS
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

    assert generated == 4
    assert rendered == [
        tmp_path / "acme" / "lamp" / "brightness.png",
        tmp_path / "acme" / "lamp" / "brightness.svg",
        tmp_path / "acme" / "speaker" / "calibration.png",
        tmp_path / "acme" / "speaker" / "calibration.svg",
    ]


@pytest.mark.parametrize(
    "composite_config",
    [
        [{"linear": {"calibrate": ["0 -> 1.0", "100 -> 5.0"]}}],
        {
            "mode": "sum_all",
            "strategies": [{"linear": {"calibrate": ["0 -> 1.0", "100 -> 5.0"]}}],
        },
    ],
)
def test_generate_directory_plots_includes_composite_calibration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    composite_config: object,
) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": composite_config,
            },
        ),
        encoding="utf-8",
    )
    rendered: list[Path] = []
    monkeypatch.setattr(cli, "render_plot", lambda _plot, output: rendered.append(output))
    monkeypatch.setattr(cli, "render_composite_diagram", lambda _diagram, output: rendered.append(output))

    assert cli.generate_directory_plots(tmp_path) == 4
    assert rendered == [
        tmp_path / "calibration.png",
        tmp_path / "calibration.svg",
        tmp_path / "composite.png",
        tmp_path / "composite.svg",
    ]


def test_generate_directory_plots_includes_composite_without_linear_calibration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": [{"fixed": {"power": 2.5}}],
            },
        ),
        encoding="utf-8",
    )
    rendered: list[Path] = []
    monkeypatch.setattr(cli, "render_composite_diagram", lambda _diagram, output: rendered.append(output))

    assert cli.generate_directory_plots(tmp_path) == 2
    assert rendered == [tmp_path / "composite.png", tmp_path / "composite.svg"]


def test_generate_directory_plots_skips_existing_composite_outputs(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text(
        '{"calculation_strategy":"composite","composite_config":[{"fixed":{"power":2}}]}',
        encoding="utf-8",
    )
    (tmp_path / "composite.png").write_bytes(b"existing")
    (tmp_path / "composite.svg").write_bytes(b"existing")

    assert cli.generate_directory_plots(tmp_path) == 0


@pytest.mark.parametrize(
    "output, expected",
    [(None, None), ("auto", Path("composite.png")), ("flow.svg", Path("flow.svg"))],
)
def test_composite_output_path(output: str | None, expected: Path | None) -> None:
    assert cli.composite_output_path(output) == expected


def test_main_renders_composite_diagram(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        '{"calculation_strategy":"composite","composite_config":[{"fixed":{"power":2}}]}',
        encoding="utf-8",
    )
    rendered: list[Path | None] = []
    monkeypatch.setattr(cli, "render_composite_diagram", lambda _diagram, output: rendered.append(output))

    cli.main([str(model), "--kind=composite", "--output=auto"])

    assert rendered == [Path("composite.png")]


def test_main_rejects_colormode_for_composite_diagram(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        cli.main([str(model), "--kind=composite", "--colormode=brightness"])


def test_generate_directory_plots_ignores_invalid_model_json(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text("invalid", encoding="utf-8")

    assert cli.generate_directory_plots(tmp_path) == 0


def test_generate_directory_plots_skips_existing_output_unless_forced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brightness = tmp_path / "brightness.csv"
    png = tmp_path / "brightness.png"
    svg = tmp_path / "brightness.svg"
    brightness.write_text("bri,watt\n1,1.0\n", encoding="utf-8")
    png.write_bytes(b"existing")
    svg.write_bytes(b"existing")
    rendered: list[Path] = []
    monkeypatch.setattr(cli, "render_plot", lambda _plot, path: rendered.append(path))

    assert cli.generate_directory_plots(tmp_path) == 0
    assert cli.generate_directory_plots(tmp_path, force=True) == 2
    assert rendered == [png, svg]


def test_generate_directory_plots_adds_missing_format_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brightness = tmp_path / "brightness.csv"
    brightness.write_text("bri,watt\n1,1.0\n", encoding="utf-8")
    (tmp_path / "brightness.png").write_bytes(b"existing")
    rendered: list[Path] = []
    monkeypatch.setattr(cli, "render_plot", lambda _plot, path: rendered.append(path))

    assert cli.generate_directory_plots(tmp_path) == 1
    assert rendered == [tmp_path / "brightness.svg"]


def test_generate_directory_plots_downsamples_svg_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brightness = tmp_path / "brightness.csv"
    rows = "".join(f"{index},{index / 10}\n" for index in range(_SVG_MAX_POINTS + 500))
    brightness.write_text(f"bri,watt\n{rows}", encoding="utf-8")
    rendered: dict[str, int] = {}
    monkeypatch.setattr(
        cli,
        "render_plot",
        lambda plot, path: rendered.__setitem__(path.suffix, sum(len(series.points) for series in plot.series)),
    )

    cli.generate_directory_plots(tmp_path)

    assert rendered[".png"] == _SVG_MAX_POINTS + 500
    assert rendered[".svg"] == _SVG_MAX_POINTS


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
