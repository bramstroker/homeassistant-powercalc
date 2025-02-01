from __future__ import annotations

import os
from typing import Any

import inquirer
from phue import Bridge, PhueRegistrationException

from measure.const import PROJECT_DIR
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.controller.light.errors import LightControllerError, ModelNotDiscoveredError

TYPE_LIGHT = "light"
TYPE_GROUP = "group"


class HueLightController(LightController):
    def __init__(self, bridge_ip: str) -> None:
        self.bridge = self.initialize_hue_bridge(bridge_ip)
        self.lights = {light.light_id: light.name for light in self.bridge.lights}
        self.groups = {group.group_id: group.name for group in self.bridge.groups}
        self.is_group: bool = False
        self.light_id: int | None = None

    def change_light_state(
        self,
        lut_mode: LutMode,
        on: bool = True,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        kwargs["on"] = on
        if self.is_group:
            self.bridge.set_group(self.light_id, kwargs)
        else:
            self.bridge.set_light(self.light_id, kwargs)

    def get_light_info(self) -> LightInfo:
        if self.is_group:
            model_id = self.find_group_model(self.light_id)
            return LightInfo(
                model_id=model_id,
            )

        # Individual light information
        light = self.bridge.get_light(self.light_id)
        light_info = LightInfo(
            model_id=light["modelid"],
        )

        if "ct" in light["capabilities"]["control"]:
            light_info.min_mired = light["capabilities"]["control"]["ct"]["min"]
            light_info.max_mired = light["capabilities"]["control"]["ct"]["max"]

        return light_info

    def find_group_model(self, group_id: int) -> str:
        model_ids = set()
        for light_id in self.bridge.get_group(group_id, "lights"):
            light = self.bridge.get_light(int(light_id))
            model_id = light["modelid"]
            model_ids.add(model_id)

        if len(model_ids) == 0:
            raise ModelNotDiscoveredError("Could not find a model id for the group")

        if len(model_ids) > 1:
            raise LightControllerError(
                "The Hue group contains lights of multiple models, this is not supported",
            )

        return model_ids.pop()

    @staticmethod
    def initialize_hue_bridge(bridge_ip: str) -> Bridge:
        config_file_path = os.path.join(
            PROJECT_DIR,
            ".persistent/.python_hue",
        )
        try:
            bridge = Bridge(ip=bridge_ip, config_file_path=config_file_path)
        except PhueRegistrationException:
            print("Please click the link button on the bridge, than hit enter..")
            input()
            bridge = Bridge(ip=bridge_ip, config_file_path=config_file_path)

        return bridge

    def get_questions(self) -> list[inquirer.questions.Question]:
        def get_message(answers: dict[str, Any]) -> str:
            if answers.get("multiple_lights"):
                return "Select the lightgroup"
            return "Select the light"

        def get_light_list(answers: dict[str, Any]) -> list:
            if answers.get("multiple_lights"):
                return [(name, f"{TYPE_GROUP}:{group_id}") for group_id, name in self.groups.items()]
            return [(name, f"{TYPE_LIGHT}:{light_id}") for light_id, name in self.lights.items()]

        return [
            inquirer.List(name="light", message=get_message, choices=get_light_list),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        light_type, light_id = answers["light"].split(":")
        self.is_group = light_type == TYPE_GROUP
        self.light_id = int(light_id)

    def has_effect_support(self) -> bool:
        return False

    def get_effect_list(self) -> list[str]:
        return []
