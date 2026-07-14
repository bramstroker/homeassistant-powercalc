from __future__ import annotations

import ast
from pathlib import Path

MEASURE_ROOT = Path(__file__).parents[1] / "measure"
COMPATIBILITY_MODULES = {"measure.py"}
EXECUTION_BOUNDARIES = {
    Path("cli/main.py"),
    Path("cli/measurements.py"),
    Path("cli/questions.py"),
    Path("cli/request_adapter.py"),
    Path("ha_app/service.py"),
}


def test_shared_modules_do_not_import_transport_packages() -> None:
    violations: list[str] = []
    for path in MEASURE_ROOT.rglob("*.py"):
        relative = path.relative_to(MEASURE_ROOT)
        if relative.parts[0] in {"cli", "ha_app"} or relative.name in COMPATIBILITY_MODULES:
            continue
        violations.extend(
            f"{relative}: {imported}"
            for imported in _imports(path)
            if imported == "inquirer" or imported.startswith(("measure.cli", "measure.ha_app"))
        )

    assert violations == []


def test_transports_do_not_construct_runners_or_device_adapters() -> None:
    forbidden_prefixes = (
        "measure.runner.average",
        "measure.runner.charging",
        "measure.runner.fan",
        "measure.runner.light",
        "measure.runner.recorder",
        "measure.runner.speaker",
        "measure.controller.charging.dummy",
        "measure.controller.charging.hass",
        "measure.controller.fan.dummy",
        "measure.controller.fan.hass",
        "measure.controller.light.dummy",
        "measure.controller.light.hass",
        "measure.controller.light.hue",
        "measure.controller.media.dummy",
        "measure.controller.media.hass",
        "measure.powermeter.dummy",
        "measure.powermeter.hass",
        "measure.powermeter.kasa",
        "measure.powermeter.manual",
        "measure.powermeter.mystrom",
        "measure.powermeter.ocr",
        "measure.powermeter.shelly",
        "measure.powermeter.tasmota",
        "measure.powermeter.tuya",
    )
    violations = [
        f"{relative}: {imported}"
        for relative in EXECUTION_BOUNDARIES
        for imported in _imports(MEASURE_ROOT / relative)
        if imported.startswith(forbidden_prefixes)
    ]

    assert violations == []


def test_transports_do_not_write_profile_models() -> None:
    violations = [
        str(relative) for relative in EXECUTION_BOUNDARIES if "measure.model" in _imports(MEASURE_ROOT / relative)
    ]

    assert violations == []


def test_production_components_do_not_process_raw_question_answers() -> None:
    violations: list[str] = []
    for path in MEASURE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            raw_answer_method = (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "process_answers"
            )
            raw_option_attribute = isinstance(node, ast.Attribute) and node.attr in {
                "controller_options",
                "power_meter_options",
            }
            if raw_answer_method or raw_option_attribute:
                violations.append(str(path.relative_to(MEASURE_ROOT)))

    assert violations == []


def test_only_home_assistant_manager_constructs_websocket_clients() -> None:
    violations: list[str] = []
    for path in MEASURE_ROOT.rglob("*.py"):
        if path.name == "home_assistant.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                name = None
            if name == "HomeAssistantWebsocketClient":
                violations.append(str(path.relative_to(MEASURE_ROOT)))

    assert violations == []


def test_runtime_service_bundle_is_not_reintroduced() -> None:
    assert not (MEASURE_ROOT / "runtime.py").exists()
    assert all("measure.runtime" not in _imports(path) for path in MEASURE_ROOT.rglob("*.py"))


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports
