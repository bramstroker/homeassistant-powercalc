import json
from pathlib import Path

from measure.visualization import CompositeDiagramError, build_composite_diagram_from_file, build_plot_from_file
from measure.visualization.profile import load_model_data
import pytest


def test_sub_profile_inherits_strategy_and_device_type(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text(
        json.dumps({"calculation_strategy": "composite", "device_type": "vacuum_robot"}),
    )
    child = tmp_path / "warm" / "model.json"
    child.parent.mkdir()
    child.write_text(
        json.dumps({"composite_config": [{"linear": {"calibrate": ["15 -> 23", "99 -> 16"]}}]}),
    )

    plot = build_plot_from_file(child)
    diagram = build_composite_diagram_from_file(child)

    assert plot.title == "Charging calibration"
    assert plot.x_label == "Battery level (%)"
    assert [(point.x, point.y) for point in plot.series[0].points] == [(15, 23), (99, 16)]
    assert len(diagram.branches) == 1
    assert diagram.branches[0].strategy == "Linear"


def test_sub_profile_replaces_parent_strategy_configuration(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text(
        json.dumps({"calculation_strategy": "composite", "composite_config": [{"fixed": {"power": 100}}]}),
    )
    child = tmp_path / "warm" / "model.json"
    child.parent.mkdir()
    child.write_text(
        json.dumps({"composite_config": {"mode": "sum_all", "strategies": [{"fixed": {"power": 5}}]}}),
    )

    diagram = build_composite_diagram_from_file(child)

    assert diagram.mode == "sum_all"
    assert [branch.detail for branch in diagram.branches] == ["5 W"]


@pytest.mark.parametrize("parent", [None, []])
def test_non_object_parent_does_not_replace_model_data(tmp_path: Path, parent: object) -> None:
    (tmp_path / "model.json").write_text(json.dumps(parent))
    child = tmp_path / "warm" / "model.json"
    child.parent.mkdir()
    child.write_text('{"calculation_strategy":"composite","composite_config":[{"fixed":{"power":5}}]}')

    assert build_composite_diagram_from_file(child).branches[0].detail == "5 W"


def test_non_object_sub_profile_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text('{"calculation_strategy":"composite"}')
    child = tmp_path / "warm" / "model.json"
    child.parent.mkdir()
    child.write_text("[]")

    with pytest.raises(CompositeDiagramError, match="does not contain a composite calculation strategy"):
        build_composite_diagram_from_file(child)


def test_other_json_artifacts_do_not_inherit_profile_data(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text('{"name":"Parent"}')
    child = tmp_path / "session" / "artifact.json"
    child.parent.mkdir()
    child.write_text('{"name":"Session"}')

    assert load_model_data(child) == {"name": "Session"}


def test_invalid_parent_json_is_reported(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text("invalid")
    child = tmp_path / "warm" / "model.json"
    child.parent.mkdir()
    child.write_text("{}")

    with pytest.raises(json.JSONDecodeError):
        load_model_data(child)
