"""Build frontend-neutral diagrams for composite power profiles."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path


class CompositeMode(StrEnum):
    STOP_AT_FIRST = "stop_at_first"
    SUM_ALL = "sum_all"


@dataclass(frozen=True, slots=True)
class CompositeBranch:
    index: int
    condition: str | None
    strategy: str
    detail: str | None


@dataclass(frozen=True, slots=True)
class CompositeDiagramSpec:
    title: str
    mode: CompositeMode
    source: str
    branches: tuple[CompositeBranch, ...]


class CompositeDiagramError(ValueError):
    """Raised when a model cannot produce a composite diagram."""


def build_composite_diagram_from_file(path: str | Path) -> CompositeDiagramSpec:
    """Build a composite branch diagram from a model.json artifact."""

    file_path = Path(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("calculation_strategy") != "composite":
        raise CompositeDiagramError("model does not contain a composite calculation strategy")

    mode, strategies = _composite_config(data.get("composite_config"))
    branches = tuple(
        branch
        for index, strategy in enumerate(strategies, start=1)
        if (branch := _composite_branch(index, strategy)) is not None
    )
    if not branches:
        raise CompositeDiagramError("model does not contain composite branches")

    return CompositeDiagramSpec(
        title="Composite strategy branches",
        mode=mode,
        source=file_path.name,
        branches=branches,
    )


def model_has_composite_branches(data: object) -> bool:
    """Return whether parsed model data contains drawable composite branches."""

    if not isinstance(data, dict) or data.get("calculation_strategy") != "composite":
        return False
    _, strategies = _composite_config(data.get("composite_config"))
    return any(_composite_branch(index, strategy) is not None for index, strategy in enumerate(strategies, start=1))


def _composite_config(config: object) -> tuple[CompositeMode, list[object]]:
    if isinstance(config, list):
        return CompositeMode.STOP_AT_FIRST, config
    if not isinstance(config, dict):
        return CompositeMode.STOP_AT_FIRST, []

    mode_value = config.get("mode", CompositeMode.STOP_AT_FIRST)
    try:
        mode = CompositeMode(mode_value)
    except ValueError:
        mode = CompositeMode.STOP_AT_FIRST
    strategies = config.get("strategies")
    return mode, strategies if isinstance(strategies, list) else []


def _composite_branch(index: int, config: object) -> CompositeBranch | None:
    if not isinstance(config, dict):
        return None
    strategy = _strategy_name(config)
    if strategy is None:
        return None
    return CompositeBranch(
        index=index,
        condition=_condition_label(config.get("condition")),
        strategy=_strategy_label(strategy),
        detail=_strategy_detail(strategy, config.get(strategy)),
    )


def _strategy_name(config: Mapping[str, object]) -> str | None:
    for strategy in ("linear", "fixed", "multi_switch", "playbook", "wled", "lut"):
        if strategy in config:
            return strategy
    return None


def _strategy_label(strategy: str) -> str:
    return {
        "lut": "LUT",
        "wled": "WLED",
        "multi_switch": "Multi-switch",
    }.get(strategy, strategy.replace("_", " ").title())


def _strategy_detail(strategy: str, config: object) -> str | None:
    if not isinstance(config, dict):
        return None
    detail_builder = {
        "linear": _linear_detail,
        "fixed": _fixed_detail,
        "playbook": _playbook_detail,
        "multi_switch": _multi_switch_detail,
    }.get(strategy)
    return detail_builder(config) if detail_builder else None


def _linear_detail(config: Mapping[str, object]) -> str | None:
    calibrate = config.get("calibrate")
    return f"{len(calibrate)} calibration points" if isinstance(calibrate, list) else None


def _fixed_detail(config: Mapping[str, object]) -> str | None:
    power = config.get("power")
    if isinstance(power, int | float) and not isinstance(power, bool):
        return f"{power:g} W"
    states_power = config.get("states_power")
    return f"{len(states_power)} state values" if isinstance(states_power, dict) else None


def _playbook_detail(config: Mapping[str, object]) -> str | None:
    playbooks = config.get("playbooks")
    if not isinstance(playbooks, dict):
        return None
    return f"{len(playbooks)} playbook{'s' if len(playbooks) != 1 else ''}"


def _multi_switch_detail(config: Mapping[str, object]) -> str | None:
    entities = config.get("entities")
    return f"{len(entities)} switches" if isinstance(entities, list) else None


def _condition_label(condition: object) -> str | None:
    if not isinstance(condition, dict):
        return None

    condition_type = condition.get("condition")
    if condition_type in {"and", "or", "not"}:
        return _compound_condition_label(str(condition_type), condition.get("conditions"))
    if condition_type == "state":
        return _state_condition_label(condition)
    if condition_type == "numeric_state":
        return _numeric_condition_label(condition)
    if condition_type == "template":
        return "Template condition"
    if condition_type == "device":
        return "Device condition"
    return str(condition_type).replace("_", " ").title() if isinstance(condition_type, str) else "Condition"


def _compound_condition_label(condition_type: str, conditions: object) -> str:
    if not isinstance(conditions, list):
        return condition_type.replace("_", " ").title()
    labels = [label for item in conditions if (label := _condition_label(item))]
    if not labels:
        return condition_type.replace("_", " ").title()
    if condition_type == "not":
        return f"NOT ({' AND '.join(labels)})"
    return f" {condition_type.upper()} ".join(labels)


def _state_condition_label(condition: Mapping[str, object]) -> str:
    subject = condition.get("attribute") or _entity_label(condition.get("entity_id"))
    state = condition.get("state")
    if subject and state is not None:
        return f"{str(subject).replace('_', ' ')} = {_value_label(state)}"
    return "State condition"


def _numeric_condition_label(condition: Mapping[str, object]) -> str:
    subject = condition.get("attribute") or _entity_label(condition.get("entity_id"))
    bounds = []
    if "above" in condition:
        bounds.append(f"> {condition['above']}")
    if "below" in condition:
        bounds.append(f"< {condition['below']}")
    if subject and bounds:
        return f"{str(subject).replace('_', ' ')} {' and '.join(bounds)}"
    return "Numeric state condition"


def _entity_label(entity_id: object) -> str | None:
    if isinstance(entity_id, list):
        entity_id = entity_id[0] if entity_id else None
    if not isinstance(entity_id, str):
        return None
    if entity_id == "[[entity]]":
        return "state"
    if entity_id.startswith("[[") and entity_id.endswith("]]"):
        entity_id = entity_id[2:-2]
    _, separator, value = entity_id.partition(":")
    return (value if separator else entity_id).replace("_", " ")


def _value_label(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
