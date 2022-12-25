import logging

from .hass import HassLightController
from .hue import HueLightController
from .dummy import DummyLightController
from .const import LightControllerType
from .controller import LightController
import config

_LOGGER = logging.getLogger("measure")


class LightControllerFactory:
    @staticmethod
    def hass():
        return HassLightController(config.HASS_URL, config.HASS_TOKEN)

    @staticmethod
    def hue():
        return HueLightController(config.HUE_BRIDGE_IP)

    @staticmethod
    def dummy():
        return DummyLightController()

    def create(self) -> LightController:
        """Create the light controller instance"""
        factories = {
            LightControllerType.DUMMY: self.dummy,
            LightControllerType.HUE: self.hue,
            LightControllerType.HASS: self.hass
        }
        factory = factories.get(config.SELECTED_LIGHT_CONTROLLER)
        if factory is None:
            raise Exception(f"Could not find a factory for {config.SELECTED_LIGHT_CONTROLLER}")

        return factory()
