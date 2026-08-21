import json
from pathlib import Path

from measure.visualization import (
    CompositeDiagramError,
    CompositeMode,
    build_composite_diagram_from_file,
    model_has_composite_branches,
)
import pytest


def test_builds_stop_at_first_composite_diagram(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": [
                    {
                        "condition": {
                            "condition": "and",
                            "conditions": [
                                {"condition": "state", "entity_id": "[[entity]]", "state": "docked"},
                                {
                                    "condition": "state",
                                    "entity_id": "[[entity_by_translation_key:charging_state]]",
                                    "state": "on",
                                },
                            ],
                        },
                        "linear": {"calibrate": ["0 -> 1", "100 -> 5"]},
                    },
                    {"fixed": {"power": 2.6}},
                    {"lut": {}},
                ],
            },
        ),
        encoding="utf-8",
    )

    diagram = build_composite_diagram_from_file(model)

    assert diagram.mode is CompositeMode.STOP_AT_FIRST
    assert diagram.source == "model.json"
    assert [(branch.strategy, branch.detail) for branch in diagram.branches] == [
        ("Linear", "2 calibration points"),
        ("Fixed", "2.6 W"),
        ("LUT", None),
    ]
    assert diagram.branches[0].condition == "state = docked AND charging state = on"
    assert diagram.branches[1].condition is None


def test_builds_sum_all_diagram_with_supported_strategy_details(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": {
                    "mode": "sum_all",
                    "strategies": [
                        {
                            "condition": {
                                "condition": "numeric_state",
                                "entity_id": "sensor.power",
                                "above": 5,
                                "below": 10,
                            },
                            "fixed": {"states_power": {"on": 4, "off": 1}},
                        },
                        {"condition": {"condition": "template"}, "playbook": {"playbooks": {"start": "run.csv"}}},
                        {
                            "condition": {"condition": "device"},
                            "multi_switch": {"entities": ["switch.one", "switch.two"]},
                        },
                        {"condition": {"condition": "not", "conditions": [{"condition": "template"}]}, "wled": {}},
                    ],
                },
            },
        ),
        encoding="utf-8",
    )

    diagram = build_composite_diagram_from_file(model)

    assert diagram.mode is CompositeMode.SUM_ALL
    assert [(branch.strategy, branch.detail, branch.condition) for branch in diagram.branches] == [
        ("Fixed", "2 state values", "sensor.power > 5 and < 10"),
        ("Playbook", "1 playbook", "Template condition"),
        ("Multi-switch", "2 switches", "Device condition"),
        ("WLED", None, "NOT (Template condition)"),
    ]


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"calculation_strategy": "linear"},
        {"calculation_strategy": "composite", "composite_config": None},
        {"calculation_strategy": "composite", "composite_config": ["invalid", {}]},
    ],
)
def test_model_without_composite_branches_is_not_supported(data: object) -> None:
    assert model_has_composite_branches(data) is False


def test_invalid_mode_falls_back_and_invalid_branches_are_skipped(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    data = {
        "calculation_strategy": "composite",
        "composite_config": {
            "mode": "invalid",
            "strategies": ["invalid", {}, {"fixed": {"power": True}}, {"linear": {}}],
        },
    }
    model.write_text(json.dumps(data), encoding="utf-8")

    diagram = build_composite_diagram_from_file(model)

    assert model_has_composite_branches(data) is True
    assert diagram.mode is CompositeMode.STOP_AT_FIRST
    assert [(branch.strategy, branch.detail) for branch in diagram.branches] == [("Fixed", None), ("Linear", None)]


def test_handles_incomplete_optional_details_and_conditions(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": [
                    {"condition": {"condition": "or"}, "lut": []},
                    {"condition": {"condition": "and", "conditions": [None]}, "playbook": {}},
                    {"condition": {"condition": "state"}, "fixed": {}},
                    {"condition": {"condition": "numeric_state"}, "linear": {}},
                    {"condition": {"condition": "custom_type"}, "wled": {}},
                    {
                        "condition": {"condition": "state", "entity_id": [], "state": ["on", "idle"]},
                        "multi_switch": {},
                    },
                    {
                        "condition": {"condition": "state", "attribute": "modes", "state": ["on", "idle"]},
                        "lut": {},
                    },
                    {
                        "condition": {"condition": "state", "attribute": "oscillating", "state": True},
                        "fixed": {"power": 1},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    diagram = build_composite_diagram_from_file(model)

    assert [(branch.strategy, branch.detail, branch.condition) for branch in diagram.branches] == [
        ("LUT", None, "Or"),
        ("Playbook", None, "And"),
        ("Fixed", None, "State condition"),
        ("Linear", None, "Numeric state condition"),
        ("WLED", None, "Custom Type"),
        ("Multi-switch", None, "State condition"),
        ("LUT", None, "modes = on, idle"),
        ("Fixed", "1 W", "oscillating = true"),
    ]


@pytest.mark.parametrize(
    "data, message",
    [
        ({"calculation_strategy": "linear"}, "does not contain a composite calculation strategy"),
        ({"calculation_strategy": "composite", "composite_config": []}, "does not contain composite branches"),
    ],
)
def test_rejects_model_without_drawable_composite(tmp_path: Path, data: object, message: str) -> None:
    model = tmp_path / "model.json"
    model.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CompositeDiagramError, match=message):
        build_composite_diagram_from_file(model)
