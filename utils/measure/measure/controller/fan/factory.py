import logging

from measure.config import MeasureConfig
from measure.controller.fan.const import FanControllerType
from measure.controller.fan.controller import FanController
from measure.controller.fan.dummy import DummyFanController
from measure.controller.fan.hass import HassFanController

_LOGGER = logging.getLogger("measure")


class FanControllerFactory:
    def __init__(self, config: MeasureConfig) -> None:
        self.config = config

    def hass(self) -> HassFanController:
        return HassFanController(self.config.hass_url, self.config.hass_token)

    @staticmethod
    def dummy() -> DummyFanController:
        return DummyFanController()

    def create(self) -> FanController:
        """Create the fan controller instance"""
        factories = {
            FanControllerType.DUMMY: self.dummy,
            FanControllerType.HASS: self.hass,
        }
        factory = factories.get(self.config.selected_fan_controller)
        if factory is None:
            raise Exception(
                f"Could not find a factory for {self.config.selected_charging_controller}",
            )

        return factory()
