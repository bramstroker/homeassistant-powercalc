from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
from typing import Any

import aiohttp
from aiohue.errors import Unauthorized
from measure.controller.light.const import LutMode
from measure.controller.light.errors import ApiConnectionError, LightControllerError
import measure.controller.light.hue as hue_module
from measure.controller.light.hue import HueLightController
import pytest


class _Items:
    def __init__(self, resources: list[Any]) -> None:
        self._resources = {resource.id: resource for resource in resources}

    @property
    def items(self) -> list[Any]:
        return list(self._resources.values())

    def __getitem__(self, resource_id: str) -> Any:  # noqa: ANN401
        return self._resources[resource_id]


class _Light:
    def __init__(
        self,
        light_id: str,
        name: str,
        model_id: str,
        *,
        color_temperature: dict[str, int] | None = None,
    ) -> None:
        self.id = light_id
        self.name = name
        self.modelid = model_id
        self.controlcapabilities = {"ct": color_temperature} if color_temperature is not None else {}
        self.calls: list[dict[str, Any]] = []
        self.failures: list[Exception] = []

    async def set_state(self, **kwargs: Any) -> None:  # noqa: ANN401
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)


class _Group:
    def __init__(self, group_id: str, name: str, lights: list[str]) -> None:
        self.id = group_id
        self.name = name
        self.lights = lights
        self.calls: list[dict[str, Any]] = []

    async def set_action(self, **kwargs: Any) -> None:  # noqa: ANN401
        self.calls.append(kwargs)


class _Bridge:
    def __init__(
        self,
        lights: list[_Light],
        groups: list[_Group],
        *,
        initialize_error: Exception | None = None,
    ) -> None:
        self.lights = _Items(lights)
        self.groups = _Items(groups)
        self.initialize_error = initialize_error
        self.initialized = False
        self.closed = False

    async def initialize(self) -> None:
        self.initialized = True
        if self.initialize_error is not None:
            raise self.initialize_error

    async def close(self) -> None:
        self.closed = True


def _resources() -> tuple[list[_Light], list[_Group]]:
    lights = [
        _Light("1", "Desk", "LCT010", color_temperature={"min": 153, "max": 500}),
        _Light("2", "Ceiling", "LCT010"),
    ]
    return lights, [_Group("12", "Office", ["1", "2"])]


def _controller(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    target: str = "light:1",
    bridge: _Bridge | None = None,
) -> tuple[HueLightController, _Bridge]:
    lights, groups = _resources()
    bridge = bridge or _Bridge(lights, groups)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    config_path = tmp_path / ".python_hue"
    config_path.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")
    return (
        HueLightController("192.0.2.10", light=target, config_file_path=config_path),
        bridge,
    )


def test_reuses_existing_bridge_registration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups)
    constructor_calls: list[tuple[str, str]] = []

    def bridge_factory(host: str, app_key: str) -> _Bridge:
        constructor_calls.append((host, app_key))
        return bridge

    monkeypatch.setattr(hue_module, "HueBridgeV1", bridge_factory)
    config_path = tmp_path / ".python_hue"
    config_path.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")

    with closing(HueLightController("192.0.2.10", light="light:1", config_file_path=config_path)) as controller:
        assert controller.lights == {1: "Desk", 2: "Ceiling"}
        assert controller.groups == {12: "Office"}

    assert constructor_calls == [("192.0.2.10", "existing-key")]
    assert bridge.initialized
    assert bridge.closed


def test_replaces_an_unauthorized_registration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lights, groups = _resources()
    stale_bridge = _Bridge(lights, groups, initialize_error=Unauthorized())
    registered_bridge = _Bridge(lights, groups)
    bridges = iter([stale_bridge, registered_bridge])
    constructor_calls: list[tuple[str, str]] = []

    def bridge_factory(host: str, app_key: str) -> _Bridge:
        constructor_calls.append((host, app_key))
        return next(bridges)

    async def create_app_key(host: str, device_type: str) -> str:
        assert (host, device_type) == ("192.0.2.10", "powercalc_measure#cli")
        return "new-key"

    monkeypatch.setattr(hue_module, "HueBridgeV1", bridge_factory)
    monkeypatch.setattr(hue_module, "create_app_key", create_app_key)
    monkeypatch.setattr("builtins.input", lambda _: "")
    config_path = tmp_path / ".python_hue"
    config_path.write_text(json.dumps({"192.0.2.10": {"username": "stale-key"}}), encoding="utf-8")

    HueLightController("192.0.2.10", light="light:1", config_file_path=config_path).close()

    assert constructor_calls == [
        ("192.0.2.10", "stale-key"),
        ("192.0.2.10", "new-key"),
    ]
    assert stale_bridge.closed
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "192.0.2.10": {"username": "new-key"},
    }


@pytest.mark.parametrize(
    ("target", "mode", "kwargs", "expected"),
    [
        ("light:1", LutMode.BRIGHTNESS, {"bri": 100}, {"on": True, "bri": 100}),
        ("light:1", LutMode.COLOR_TEMP, {"bri": 100, "ct": 250}, {"on": True, "bri": 100, "ct": 250}),
        (
            "light:1",
            LutMode.HS,
            {"bri": 100, "hue": 32000, "sat": 200},
            {"on": True, "bri": 100, "hue": 32000, "sat": 200},
        ),
        ("group:12", LutMode.BRIGHTNESS, {"bri": 80}, {"on": True, "bri": 80}),
    ],
)
def test_forwards_v1_light_state_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target: str,
    mode: LutMode,
    kwargs: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    controller, bridge = _controller(monkeypatch, tmp_path, target=target)
    with closing(controller):
        controller.change_light_state(mode, **kwargs)
        resource = bridge.groups["12"] if target.startswith("group:") else bridge.lights["1"]
        assert resource.calls == [expected]


def test_retries_transient_connection_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, bridge = _controller(monkeypatch, tmp_path)
    light = bridge.lights["1"]
    light.failures = [aiohttp.ClientConnectionError(), aiohttp.ClientConnectionError()]

    with closing(controller):
        controller.change_light_state(LutMode.BRIGHTNESS, bri=100)

    assert len(light.calls) == 3


def test_raises_after_three_connection_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, bridge = _controller(monkeypatch, tmp_path)
    light = bridge.lights["1"]
    light.failures = [aiohttp.ClientConnectionError() for _ in range(3)]

    with closing(controller), pytest.raises(ApiConnectionError, match="after 3 attempts"):
        controller.change_light_state(LutMode.BRIGHTNESS, bri=100)


def test_reads_model_and_color_temperature_bounds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    with closing(controller):
        info = controller.get_light_info()

    assert info.model_id == "LCT010"
    assert info.min_mired == 153
    assert info.max_mired == 500


def test_rejects_groups_with_multiple_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lights, groups = _resources()
    lights[1].modelid = "DIFFERENT"
    controller, _ = _controller(monkeypatch, tmp_path, target="group:12", bridge=_Bridge(lights, groups))

    with closing(controller), pytest.raises(LightControllerError, match="multiple models"):
        controller.get_light_info()


def test_rejects_invalid_or_missing_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    config_path = tmp_path / ".python_hue"
    config_path.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")

    with pytest.raises(LightControllerError, match="format"):
        HueLightController("192.0.2.10", light="room:12", config_file_path=config_path)

    assert bridge.closed

    with pytest.raises(LightControllerError, match="does not exist"):
        HueLightController("192.0.2.10", light="light:99", config_file_path=config_path)
