import logging

from measure.config import MeasureConfig
from measure.controller.charging.const import ChargingControllerType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.dummy import DummyChargingController
from measure.controller.charging.hass import HassChargingController

_LOGGER = logging.getLogger("measure")


class ChargingControllerFactory:
    def __init__(self, config: MeasureConfig) -> None:
        self.config = config

    def hass(self) -> HassChargingController:
        return HassChargingController(self.config.hass_url, self.config.hass_token)

    @staticmethod
    def dummy() -> DummyChargingController:
        return DummyChargingController()

    def create(self) -> ChargingController:
        """Create the charging controller instance"""
        factories = {
            ChargingControllerType.DUMMY: self.dummy,
            ChargingControllerType.HASS: self.hass,
        }
        factory = factories.get(self.config.selected_charging_controller)
        if factory is None:
            raise Exception(
                f"Could not find a factory for {self.config.selected_charging_controller}",
            )

        return factory()
