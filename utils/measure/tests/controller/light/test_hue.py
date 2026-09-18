from contextlib import closing
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
from aiohue.errors import AiohueException, Unauthorized
from measure.controller.errors import ApiConnectionError
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.errors import LightControllerError, ModelNotDiscoveredError
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
    "target, mode, kwargs, expected",
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


@pytest.mark.parametrize("has_registration", [True, False])
@pytest.mark.parametrize(
    "error", [aiohttp.ClientConnectionError("Offline"), TimeoutError("Timed out"), AiohueException("Bridge error")]
)
def test_initialization_failure_closes_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    has_registration: bool,
    error: Exception,
) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups, initialize_error=error)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    monkeypatch.setattr(hue_module, "create_app_key", AsyncMock(return_value="new-key"))
    monkeypatch.setattr("builtins.input", lambda _: "")
    config = tmp_path / ".python_hue"
    if has_registration:
        config.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")

    with pytest.raises(LightControllerError, match="Failed to connect to Hue bridge") as raised:
        HueLightController("192.0.2.10", light="light:1", config_file_path=config)

    assert raised.value.__cause__ is error
    assert bridge.closed


def test_registration_failure_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    error = aiohttp.ClientConnectionError("Offline")
    registration = AsyncMock(side_effect=error)
    constructor = MagicMock()
    monkeypatch.setattr(hue_module, "create_app_key", registration)
    monkeypatch.setattr(hue_module, "HueBridgeV1", constructor)
    monkeypatch.setattr("builtins.input", lambda _: "")
    config = tmp_path / ".python_hue"

    with pytest.raises(LightControllerError, match="Failed to register with Hue bridge") as raised:
        HueLightController("192.0.2.10", config_file_path=config)

    assert raised.value.__cause__ is error
    constructor.assert_not_called()
    assert not config.exists()


def test_unselected_controller_lists_resources_but_cannot_change_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    config = tmp_path / ".python_hue"
    config.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")

    with closing(HueLightController("192.0.2.10", config_file_path=config)) as controller:
        assert controller.lights == {1: "Desk", 2: "Ceiling"}
        assert controller.groups == {12: "Office"}
        with pytest.raises(LightControllerError, match="No Hue light or group selected"):
            controller.change_light_state(LutMode.BRIGHTNESS, bri=100)

    assert lights[0].calls == []
    assert bridge.closed


@pytest.mark.parametrize("resource", ["lights", "groups"])
def test_missing_bridge_resources_closes_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, resource: str
) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups)
    setattr(bridge, resource, None)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    config = tmp_path / ".python_hue"
    config.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")

    with pytest.raises(LightControllerError, match=f"did not return any {resource[:-1]} resources"):
        HueLightController("192.0.2.10", light="light:1", config_file_path=config)

    assert bridge.closed


def test_connection_error_is_preserved_when_bridge_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lights, groups = _resources()
    connection_error = aiohttp.ClientConnectionError("Bridge offline")
    bridge = _Bridge(lights, groups, initialize_error=connection_error)
    close_bridge = AsyncMock(side_effect=aiohttp.ClientConnectionError("Cleanup failed"))
    monkeypatch.setattr(bridge, "close", close_bridge)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    config = tmp_path / ".python_hue"
    config.write_text(json.dumps({"192.0.2.10": {"username": "existing-key"}}), encoding="utf-8")

    with pytest.raises(LightControllerError, match="Bridge offline") as raised:
        HueLightController("192.0.2.10", light="light:1", config_file_path=config)

    assert raised.value.__cause__ is connection_error
    close_bridge.assert_awaited_once()


@pytest.mark.parametrize("contents", ["{invalid json", ""])
def test_corrupt_registration_file_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contents: str) -> None:
    config = tmp_path / ".python_hue"
    config.write_text(contents, encoding="utf-8")
    constructor = MagicMock()
    monkeypatch.setattr(hue_module, "HueBridgeV1", constructor)

    with pytest.raises(LightControllerError, match="Could not read Hue bridge configuration"):
        HueLightController("192.0.2.10", config_file_path=config)

    constructor.assert_not_called()
    assert config.read_text(encoding="utf-8") == contents


def test_new_registration_preserves_other_valid_bridge_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups)
    monkeypatch.setattr(hue_module, "HueBridgeV1", lambda host, app_key: bridge)
    monkeypatch.setattr(hue_module, "create_app_key", AsyncMock(return_value="new-key"))
    monkeypatch.setattr("builtins.input", lambda _: "")
    config = tmp_path / ".python_hue"
    config.write_text(
        json.dumps(
            {
                "192.0.2.10": "invalid entry",
                "192.0.2.20": {"username": "other-key"},
                "192.0.2.30": {"username": 42},
            }
        ),
        encoding="utf-8",
    )

    with closing(HueLightController("192.0.2.10", light="light:1", config_file_path=config)):
        pass

    assert json.loads(config.read_text(encoding="utf-8")) == {
        "192.0.2.10": {"username": "new-key"},
        "192.0.2.20": {"username": "other-key"},
    }


def test_registration_save_failure_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hue_module, "create_app_key", AsyncMock(return_value="new-key"))
    monkeypatch.setattr("builtins.input", lambda _: "")
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")

    with pytest.raises(LightControllerError, match="Could not save Hue bridge configuration") as raised:
        HueLightController("192.0.2.10", config_file_path=blocker / ".python_hue")

    assert isinstance(raised.value.__cause__, OSError)


def test_bridge_state_error_is_not_retried(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, bridge = _controller(monkeypatch, tmp_path)
    error = AiohueException("Invalid state")
    bridge.lights["1"].failures = [error]

    with closing(controller), pytest.raises(LightControllerError, match="Failed to set light state") as raised:
        controller.change_light_state(LutMode.BRIGHTNESS, bri=100)

    assert raised.value.__cause__ is error
    assert bridge.lights["1"].calls == [{"on": True, "bri": 100}]


def test_group_model_and_effect_capabilities(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, _ = _controller(monkeypatch, tmp_path, target="group:12")

    with closing(controller):
        assert controller.get_light_info().model_id == "LCT010"
        assert controller.has_effect_support() is False
        assert controller.get_effect_list() == []


def test_empty_group_has_no_discoverable_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lights, _ = _resources()
    bridge = _Bridge(lights, [_Group("12", "Empty", [])])
    controller, _ = _controller(monkeypatch, tmp_path, target="group:12", bridge=bridge)

    with closing(controller), pytest.raises(ModelNotDiscoveredError, match="Could not find a model id"):
        controller.get_light_info()


def test_light_without_color_temperature_bounds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, _ = _controller(monkeypatch, tmp_path, target="light:2")

    with closing(controller):
        info = controller.get_light_info()

    assert info.model_id == "LCT010"
    assert info.min_mired == MIN_MIRED
    assert info.max_mired == MAX_MIRED


def test_target_without_separator_is_rejected_and_bridge_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lights, groups = _resources()
    bridge = _Bridge(lights, groups)

    with pytest.raises(LightControllerError, match="format"):
        _controller(monkeypatch, tmp_path, target="light", bridge=bridge)

    assert bridge.closed


def test_close_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller, bridge = _controller(monkeypatch, tmp_path)
    close = AsyncMock(wraps=bridge.close)
    monkeypatch.setattr(bridge, "close", close)

    controller.close()
    controller.close()

    close.assert_awaited_once_with()
