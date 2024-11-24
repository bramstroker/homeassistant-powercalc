import logging

from measure import config
from measure.controller.charging.const import ChargingControllerType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.dummy import DummyChargingController
from measure.controller.charging.hass import HassChargingController

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
