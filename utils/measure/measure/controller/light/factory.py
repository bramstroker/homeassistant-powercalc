import logging

from measure.config import MeasureConfig
from measure.controller.light.const import LightControllerType
from measure.controller.light.controller import LightController
from measure.controller.light.dummy import DummyLightController
from measure.controller.light.hass import HassLightController
from measure.controller.light.hue import HueLightController

_LOGGER = logging.getLogger("measure")


class LightControllerFactory:
    def __init__(self, config: MeasureConfig) -> None:
        self.config = config

    def hass(self) -> HassLightController:
        return HassLightController(self.config.hass_url, self.config.hass_token, self.config.light_transition_time)

    def hue(self) -> HueLightController:
        return HueLightController(self.config.hue_bridge_ip)

    @staticmethod
    def dummy() -> DummyLightController:
        return DummyLightController()

    def create(self) -> LightController:
        """Create the light controller instance"""
        factories = {
            LightControllerType.DUMMY: self.dummy,
            LightControllerType.HUE: self.hue,
            LightControllerType.HASS: self.hass,
        }
        factory = factories.get(self.config.selected_light_controller)
        if factory is None:
            raise Exception(
                f"Could not find a factory for {self.config.selected_light_controller}",
            )

        return factory()
