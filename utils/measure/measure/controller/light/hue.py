from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import json
from pathlib import Path
from typing import Any

import aiohttp
from aiohue import HueBridgeV1, create_app_key
from aiohue.errors import AiohueException, Unauthorized
from aiohue.v1.groups import Groups
from aiohue.v1.lights import Lights

from measure.const import PROJECT_DIR
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.controller.light.errors import ApiConnectionError, LightControllerError, ModelNotDiscoveredError

TYPE_LIGHT = "light"
TYPE_GROUP = "group"
_APP_DEVICE_TYPE = "powercalc_measure#cli"


class HueLightController(LightController):
    """Synchronous measurement adapter for aiohue's maintained V1 bridge API."""

    def __init__(
        self,
        bridge_ip: str,
        *,
        light: str | None = None,
        config_file_path: Path | None = None,
    ) -> None:
        self._bridge_ip = bridge_ip
        self._config_file_path = config_file_path or Path(PROJECT_DIR) / ".persistent" / ".python_hue"
        self._async_runner = asyncio.Runner()
        self._closed = False
        try:
            self.bridge = self._initialize_bridge()
            lights = self._lights()
            groups = self._groups()
            self.lights = {int(item.id): item.name for item in lights.items}
            self.groups = {int(item.id): item.name for item in groups.items}
            self.is_group = False
            self.light_id: str | None = None
            if light is not None:
                self._select_light(light)
        except Exception:
            if hasattr(self, "bridge"):
                self._close_failed_bridge(self.bridge)
            self._async_runner.close()
            self._closed = True
            raise

    def change_light_state(
        self,
        lut_mode: LutMode,
        on: bool = True,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        del lut_mode
        for attempt in range(3):
            try:
                selected_id = self._selected_id()
                if self.is_group:
                    self._run(self._groups()[selected_id].set_action(on=on, **kwargs))
                else:
                    self._run(self._lights()[selected_id].set_state(on=on, **kwargs))
                return
            except (aiohttp.ClientError, TimeoutError) as error:
                if attempt == 2:
                    raise ApiConnectionError(f"Failed to set light state after 3 attempts: {error}") from error
            except AiohueException as error:
                raise LightControllerError(f"Failed to set light state: {error}") from error

    def get_light_info(self) -> LightInfo:
        if self.is_group:
            return LightInfo(model_id=self.find_group_model(self._selected_id()))

        light = self._lights()[self._selected_id()]
        light_info = LightInfo(model_id=str(light.modelid))
        color_temperature = light.controlcapabilities.get("ct")
        if color_temperature is not None:
            light_info.min_mired = int(color_temperature["min"])
            light_info.max_mired = int(color_temperature["max"])
        return light_info

    def find_group_model(self, group_id: int | str) -> str:
        group = self._groups()[str(group_id)]
        model_ids = {str(self._lights()[light_id].modelid) for light_id in group.lights}
        if not model_ids:
            raise ModelNotDiscoveredError("Could not find a model id for the group")
        if len(model_ids) > 1:
            raise LightControllerError("The Hue group contains lights of multiple models, this is not supported")
        return model_ids.pop()

    def has_effect_support(self) -> bool:
        return False

    def get_effect_list(self) -> list[str]:
        return []

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._run(self.bridge.close())
        finally:
            self._async_runner.close()
            self._closed = True

    def _initialize_bridge(self) -> HueBridgeV1:
        app_key = self._load_app_key()
        if app_key is not None:
            bridge = HueBridgeV1(self._bridge_ip, app_key)
            try:
                self._run(bridge.initialize())
                return bridge
            except Unauthorized:
                self._close_failed_bridge(bridge)
            except (aiohttp.ClientError, TimeoutError, AiohueException) as error:
                self._close_failed_bridge(bridge)
                raise LightControllerError(f"Failed to connect to Hue bridge: {error}") from error

        app_key = self._register_app()
        bridge = HueBridgeV1(self._bridge_ip, app_key)
        try:
            self._run(bridge.initialize())
        except (aiohttp.ClientError, TimeoutError, AiohueException) as error:
            self._close_failed_bridge(bridge)
            raise LightControllerError(f"Failed to connect to Hue bridge: {error}") from error
        return bridge

    def _register_app(self) -> str:
        input("Please click the link button on the bridge, then press enter...")
        try:
            app_key = self._run(create_app_key(self._bridge_ip, _APP_DEVICE_TYPE))
        except (aiohttp.ClientError, TimeoutError, AiohueException) as error:
            raise LightControllerError(f"Failed to register with Hue bridge: {error}") from error
        app_key = str(app_key)
        self._save_app_key(app_key)
        return app_key

    def _load_app_key(self) -> str | None:
        if not self._config_file_path.exists():
            return None
        try:
            config = json.loads(self._config_file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LightControllerError(f"Could not read Hue bridge configuration: {error}") from error
        bridge_config = config.get(self._bridge_ip, {})
        app_key = bridge_config.get("username") if isinstance(bridge_config, dict) else None
        return str(app_key) if app_key else None

    def _save_app_key(self, app_key: str) -> None:
        config = self._load_bridge_config()
        config[self._bridge_ip] = {"username": app_key}
        try:
            self._config_file_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_file_path.write_text(json.dumps(config), encoding="utf-8")
        except OSError as error:
            raise LightControllerError(f"Could not save Hue bridge configuration: {error}") from error

    def _load_bridge_config(self) -> dict[str, dict[str, str]]:
        """Return only well-formed bridge entries; anything else is dropped instead of rewritten."""
        if not self._config_file_path.exists():
            return {}
        try:
            loaded = json.loads(self._config_file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LightControllerError(f"Could not read Hue bridge configuration: {error}") from error
        if not isinstance(loaded, dict):
            return {}
        return {
            bridge_ip: {"username": entry["username"]}
            for bridge_ip, entry in loaded.items()
            if isinstance(bridge_ip, str) and isinstance(entry, dict) and isinstance(entry.get("username"), str)
        }

    def _select_light(self, light: str) -> None:
        try:
            light_type, light_id = light.split(":", maxsplit=1)
        except ValueError as error:
            raise LightControllerError("Hue target must use the format light:<id> or group:<id>") from error
        if light_type not in {TYPE_LIGHT, TYPE_GROUP}:
            raise LightControllerError("Hue target must use the format light:<id> or group:<id>")
        resources = self._groups() if light_type == TYPE_GROUP else self._lights()
        try:
            resources[light_id]
        except KeyError as error:
            raise LightControllerError(f"Hue {light_type} {light_id} does not exist") from error
        self.is_group = light_type == TYPE_GROUP
        self.light_id = light_id

    def _selected_id(self) -> str:
        if self.light_id is None:
            raise LightControllerError("No Hue light or group selected")
        return self.light_id

    def _lights(self) -> Lights:
        if self.bridge.lights is None:
            raise LightControllerError("Hue bridge did not return any light resources")
        return self.bridge.lights

    def _groups(self) -> Groups:
        if self.bridge.groups is None:
            raise LightControllerError("Hue bridge did not return any group resources")
        return self.bridge.groups

    def _run[T](self, operation: Coroutine[Any, Any, T]) -> T:
        return self._async_runner.run(operation)

    def _close_failed_bridge(self, bridge: HueBridgeV1) -> None:
        try:
            self._run(bridge.close())
        except Exception:  # noqa: BLE001 - preserve the original connection error
            return
