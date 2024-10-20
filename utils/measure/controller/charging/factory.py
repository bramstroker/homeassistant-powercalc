import logging

import config

from .const import ChargingControllerType
from .controller import ChargingController
from .dummy import DummyChargingController
from .hass import HassChargingController

_LOGGER = logging.getLogger("measure")


class ChargingControllerFactory:
    @staticmethod
    def hass() -> HassChargingController:
        return HassChargingController(config.HASS_URL, config.HASS_TOKEN)

    @staticmethod
    def dummy() -> DummyChargingController:
        return DummyChargingController()

    def create(self) -> ChargingController:
        """Create the charging controller instance"""
        factories = {
            ChargingControllerType.DUMMY: self.dummy,
            ChargingControllerType.HASS: self.hass,
        }
        factory = factories.get(config.SELECTED_CHARGING_CONTROLLER)
        if factory is None:
            raise Exception(
                f"Could not find a factory for {config.SELECTED_CHARGING_CONTROLLER}",
            )

        return factory()
