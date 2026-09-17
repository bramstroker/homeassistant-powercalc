import ast
from pathlib import Path
import subprocess
import sys

import pytest

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


@pytest.mark.parametrize(
    "module",
    [
        "measure.ha_app.storage",
        "measure.ha_app.coordinator",
        "measure.ha_app.contribution.models",
        "measure.ha_app.contribution.coordinator",
        "measure.ha_app.context",
        "measure.ha_app.routes.measurement",
        "measure.ha_app.routes.sessions",
        "measure.ha_app.routes.contribution",
        "measure.profile.output",
        "measure.profile.prepare",
        "measure.recording.files",
        "measure.runner.recorder",
        "measure.home_assistant.entities",
        "measure.utils.sampling",
    ],
)
def test_modules_import_without_relying_on_import_order(module: str) -> None:
    """A fresh process exposes cycles otherwise masked by pytest collection order."""
    result = subprocess.run(  # noqa: S603 - module names are fixed test parameters.
        [sys.executable, "-c", f"import {module}"],
        cwd=MEASURE_ROOT.parent,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "package,forbidden",
    [
        ("profile", ("measure.contribution", "measure.ha_app", "measure.cli")),
        ("recording", ("measure.analyser", "measure.runner", "measure.ha_app", "measure.cli")),
        ("runner", ("measure.execution", "measure.assembler", "measure.ha_app", "measure.cli")),
    ],
)
def test_packages_depend_on_shared_contracts_not_orchestrators(package: str, forbidden: tuple[str, ...]) -> None:
    violations = [
        f"{path.relative_to(MEASURE_ROOT)}: {imported}"
        for path in (MEASURE_ROOT / package).rglob("*.py")
        for imported in _imports(path)
        if imported.startswith(forbidden)
    ]
    assert violations == []


@pytest.mark.parametrize("package", ["contribution", "ha_app/contribution", "ha_app/routes"])
def test_workflow_packages_do_not_eagerly_import_services(package: str) -> None:
    assert _imports(MEASURE_ROOT / package / "__init__.py") == []


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
        str(relative)
        for relative in EXECUTION_BOUNDARIES
        if "measure.profile.model" in _imports(MEASURE_ROOT / relative)
    ]

    assert violations == []


def test_only_home_assistant_manager_constructs_websocket_clients() -> None:
    violations: list[str] = []
    for path in MEASURE_ROOT.rglob("*.py"):
        if path == MEASURE_ROOT / "home_assistant/client.py":
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


def test_controller_exception_names_are_defined_once() -> None:
    """Two sibling classes sharing a name make `except` clauses silently miss.

    measure.controller.errors and measure.controller.light.errors both defined an
    unrelated ApiConnectionError, so the light runner never retried a dropped
    Home Assistant connection. See issue #4543.
    """

    definitions: dict[str, list[str]] = {}
    for path in (MEASURE_ROOT / "controller").rglob("errors.py"):
        module = path.relative_to(MEASURE_ROOT).with_suffix("").as_posix().replace("/", ".")
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                definitions.setdefault(node.name, []).append(module)

    duplicates = {name: modules for name, modules in definitions.items() if len(modules) > 1}
    assert duplicates == {}
