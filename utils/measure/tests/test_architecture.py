from __future__ import annotations

import ast
from pathlib import Path

MEASURE_ROOT = Path(__file__).parents[1] / "measure"
CLI_ENTRYPOINTS = {"measure.py"}
EXECUTION_BOUNDARIES = {
    Path("cli/main.py"),
    Path("cli/measurements.py"),
    Path("cli/questions.py"),
    Path("cli/request_adapter.py"),
    Path("ha_app/service.py"),
}
OPTIONAL_ADAPTER_MODULES = {
    "measure.controller.light.hue",
    "measure.powermeter.kasa",
    "measure.powermeter.tuya",
}


def test_shared_modules_do_not_import_transport_packages() -> None:
    violations: list[str] = []
    for path in MEASURE_ROOT.rglob("*.py"):
        relative = path.relative_to(MEASURE_ROOT)
        if relative.parts[0] in {"cli", "ha_app"} or relative.name in CLI_ENTRYPOINTS:
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


def test_only_home_assistant_manager_constructs_websocket_clients() -> None:
    violations: list[str] = []
    for path in MEASURE_ROOT.rglob("*.py"):
        if path.name == "home_assistant.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(
            str(path.relative_to(MEASURE_ROOT))
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _call_name(node) in {"HomeAssistantWebsocketClient", "HomeAssistantDiscoveryClient"}
        )

    assert violations == []


def test_assembler_imports_optional_adapters_only_when_selected() -> None:
    imports = _top_level_imports(MEASURE_ROOT / "assembler.py")

    assert not imports.intersection(OPTIONAL_ADAPTER_MODULES)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
